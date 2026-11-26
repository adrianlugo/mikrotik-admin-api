# api_mikrotik/exceptions.py
"""Manejador global de errores de la API.

Todas las respuestas de error de la API usan un único formato:

    {"error": "<mensaje claro en español>", "codigo": "<clave>"}

``error`` es el mensaje que ve el usuario (en español, sin detalles
técnicos) y ``codigo`` es una clave estable que la web u otro cliente
puede usar para decidir qué mostrar o hacer. El detalle técnico
(trazas, rutas internas, mensajes crudos de la librería RouterOS)
queda SOLO en el registro del servidor (``logger.exception``) y nunca
sale en la respuesta.

Compatibilidad: antes los errores de MikroTik se devolvían como
``{"mikrotik_error": "..."}`` y los de validación como un diccionario
por campo. Ese formato ya NO se emite: la web no leía la clave
``mikrotik_error`` de forma específica (su ``api_client.py`` recorre
cualquier diccionario de error y junta sus valores), así que con la
clave ``error`` le basta; si la web quiere un mensaje limpio, debe
preferir ``error`` e ignorar ``codigo`` (ver ``docs/api.md``,
«Errores»). Las validaciones siguen incluyendo el detalle por campo
en ``detalles`` para quien lo necesite.

``LANGUAGE_CODE`` sigue siendo ``'en-us'`` en ``core/settings.py`` a
propósito: los mensajes de este manejador están escritos en español
directamente, así no dependen de las traducciones de Django/DRF, que
en inglés dirían «Not found.» o «Incorrect authentication credentials.».
Cambiar ``LANGUAGE_CODE`` a ``'es'`` afectaría a todo el proyecto
(admin, mensajes internos) y no es necesario para esto.
"""

import logging
import socket

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError as DRFValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class MikroTikError(Exception):
    """Excepción base para errores relacionados con la API de MikroTik."""
    def __init__(self, message="Ocurrió un error en el MikroTik"):
        self.message = message
        super().__init__(self.message)


class MikroTikConnectionError(MikroTikError):
    """Se lanza cuando no se puede establecer comunicación con el router."""
    pass


class MikroTikTimeoutError(MikroTikError):
    """El router no respondió dentro del tiempo configurado.

    Es hija de :class:`MikroTikError` pero se mapea a 503 (no a 502):
    el router existe y la conexión se estableció, pero no contestó a
    tiempo (ver ``MIKROTIK_TIMEOUT_SEGUNDOS`` en ``core/settings.py``).
    """

    def __init__(
        self,
        message=(
            "El router no responde a tiempo. Revisa que esté encendido y "
            "con conexión, e inténtalo de nuevo."
        ),
    ):
        super().__init__(message)


def _respuesta(error, codigo, codigo_http):
    """Una respuesta de error en el formato único de la API."""
    return Response(
        {"error": error, "codigo": codigo},
        status=codigo_http,
    )


# Traducciones de los mensajes de validación más comunes de DRF/Django,
# que por defecto salen en inglés. Solo se traduce lo que se conoce;
# cualquier otro mensaje se devuelve tal cual (los mensajes propios de
# los serializers ya están en español).
_TRADUCCIONES_VALIDACION = {
    "This field is required.": "Este campo es obligatorio.",
    "This field may not be blank.": "Este campo no puede estar vacío.",
    "This field may not be null.": "Este campo no puede ser nulo.",
    "A valid integer is required.": "Se necesita un número entero válido.",
    "A valid number is required.": "Se necesita un número válido.",
    "Enter a valid date.": "Escribe una fecha válida.",
    "Enter a valid date/time.": "Escribe una fecha y hora válidas.",
    "Enter a valid email address.": "Escribe una dirección de correo válida.",
    "Enter a valid URL.": "Escribe una URL válida.",
    "Enter a valid UUID.": "Escribe un identificador válido.",
    "Enter a valid IP address.": "Escribe una dirección IP válida.",
    "Ensure this value is greater than or equal to 0.": (
        "El valor debe ser mayor o igual que 0."
    ),
    "Not a valid string.": "No es un texto válido.",
    "Incorrect type. Expected pk value, received str.": (
        "Tipo incorrecto: se esperaba un identificador."
    ),
}


def _traducir_mensaje_validacion(mensaje):
    return _TRADUCCIONES_VALIDACION.get(str(mensaje), str(mensaje))


def _aplanar_errores_validacion(data):
    """Convierte el detalle de un ValidationError en una lista de mensajes.

    Acepta diccionarios por campo, listas y mensajes sueltos.
    """
    mensajes = []
    if isinstance(data, dict):
        for campo, errores in data.items():
            for mensaje in _aplanar_errores_validacion(errores):
                if campo not in ("non_field_errors", "__all__"):
                    mensajes.append(f"{campo}: {mensaje}")
                else:
                    mensajes.append(mensaje)
    elif isinstance(data, (list, tuple)):
        for item in data:
            mensajes.extend(_aplanar_errores_validacion(item))
    elif data is not None:
        mensajes.append(_traducir_mensaje_validacion(data))
    return mensajes


def _mensaje_o_defecto(exc, defecto, conocidos_en_ingles=()):
    """El detalle de la excepción, salvo que sea un texto por defecto en inglés.

    DRF trae sus mensajes por defecto en inglés («Not found.»,
    «Incorrect authentication credentials.», ...). En ese caso se usa el
    mensaje en español que se pasa como ``defecto``; si el código puso
    su propio mensaje (por ejemplo el de token caducado, ya en español),
    se respeta.
    """
    detalle = getattr(exc, "detail", None)
    if detalle is None:
        return defecto
    texto = str(detalle)
    if texto in conocidos_en_ingles or texto.startswith("Request was throttled"):
        return defecto
    return texto


# Mensajes por defecto en inglés de DRF, para detectarlos y sustituirlos.
# AuthenticationFailed tiene varios: credenciales incorrectas, token
# inválido y petición sin credenciales.
_DETALLES_AUTH_EN = (
    "Incorrect authentication credentials.",
    "Invalid token.",
    "Authentication credentials were not provided.",
)
_DETALLE_NO_ENCONTRADO_EN = "Not found."
_DETALLE_SIN_PERMISO_EN = "You do not have permission to perform this action."


def custom_exception_handler(exc, context):
    """
    Manejador global para interceptar errores en toda la API y
    devolverlos siempre en el formato único
    ``{"error": "...", "codigo": "..."}``.

    El detalle técnico va SOLO al registro (``logger.exception``);
    la respuesta lleva únicamente un mensaje claro en español.
    """
    # Primero dejamos que DRF maneje sus excepciones estándar
    # (ValidationError, NotFound, etc.) y partimos de su respuesta.
    response = exception_handler(exc, context)

    # --- Excepciones propias de MikroTik (no las maneja DRF) ---
    if isinstance(exc, MikroTikTimeoutError):
        logger.exception("El router no respondió a tiempo")
        return _respuesta(exc.message, "router_sin_respuesta", status.HTTP_503_SERVICE_UNAVAILABLE)
    if isinstance(exc, MikroTikError):
        logger.exception("Error de comunicación con el router MikroTik")
        return _respuesta(exc.message, "mikrotik_error", status.HTTP_502_BAD_GATEWAY)

    # --- Errores de la base de datos ---
    if isinstance(exc, ProtectedError):
        # Borrado protegido: otro registro depende de este (por ejemplo,
        # un router con clientes). 409, no 500.
        logger.exception("Borrado protegido por una relación")
        return _respuesta(
            "No se puede eliminar porque hay registros que dependen de él.",
            "borrado_protegido",
            status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, IntegrityError):
        logger.exception("Error de integridad en la base de datos")
        return _respuesta(
            "Ya existe un registro con esos datos.",
            "registro_duplicado",
            status.HTTP_400_BAD_REQUEST,
        )

    # --- Respuestas de RouterOS incompletas y datos inválidos ---
    if isinstance(exc, KeyError):
        # RouterOS no devolvió un campo esperado (por ejemplo el .id).
        logger.exception("RouterOS devolvió una respuesta incompleta")
        return _respuesta(
            "El router devolvió una respuesta incompleta.",
            "respuesta_router_invalida",
            status.HTTP_502_BAD_GATEWAY,
        )
    if isinstance(exc, DjangoValidationError):
        mensajes = _aplanar_errores_validacion(
            exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        )
        return Response(
            {
                "error": mensajes[0] if mensajes else "Los datos enviados no son válidos.",
                "codigo": "validacion",
                "detalles": mensajes,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, (TimeoutError, socket.timeout)):
        logger.exception("Tiempo de espera agotado con el router")
        return _respuesta(
            "El router no responde a tiempo. Revisa que esté encendido y "
            "con conexión, e inténtalo de nuevo.",
            "router_sin_respuesta",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if isinstance(exc, ValueError):
        # ValueError de descifrado (crypto.decrypt_value): la credencial
        # está cifrada y la clave no está configurada o es otra.
        logger.exception("Valor inválido (posible credencial sin descifrar)")
        return _respuesta(
            "No se pudo descifrar una credencial guardada. Revisa que "
            "MIKROTIK_CREDENTIALS_KEY sea la misma con la que se cifró.",
            "credencial_no_descifrable",
            status.HTTP_502_BAD_GATEWAY,
        )

    # Error de la librería RouterOS que llegó sin convertir a MikroTikError.
    try:
        from routeros_api.exceptions import RouterOsApiError
    except ImportError:  # pragma: no cover - sin la librería instalada
        RouterOsApiError = ()
    if RouterOsApiError and isinstance(exc, RouterOsApiError):
        logger.exception("Error de la librería RouterOS")
        return _respuesta(
            "El router rechazó la operación.",
            "mikrotik_error",
            status.HTTP_502_BAD_GATEWAY,
        )

    # --- Excepciones de DRF ya convertidas en respuesta ---
    if response is not None:
        if isinstance(exc, Http404):
            # DRF convierte el Http404 de get_object() en una respuesta
            # 404, pero la excepción sigue siendo Http404 (no NotFound):
            # hay que mapearla aquí para que lleve el formato único.
            return _respuesta(
                "No se encontró el recurso solicitado.",
                "no_encontrado",
                status.HTTP_404_NOT_FOUND,
            )
        if isinstance(exc, DjangoPermissionDenied):
            return _respuesta(
                "No tienes permiso para realizar esta acción.",
                "sin_permiso",
                status.HTTP_403_FORBIDDEN,
            )
        if isinstance(exc, DRFValidationError):
            mensajes = _aplanar_errores_validacion(response.data)
            return Response(
                {
                    "error": mensajes[0] if mensajes else "Los datos enviados no son válidos.",
                    "codigo": "validacion",
                    "detalles": response.data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        # NotAuthenticated es hermana de AuthenticationFailed en DRF
        # (las dos heredan de APIException): sin token llega esta.
        if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
            return _respuesta(
                _mensaje_o_defecto(
                    exc,
                    "La autenticación falló. Revisa el token e inicia sesión de nuevo.",
                    _DETALLES_AUTH_EN,
                ),
                "no_autenticado",
                status.HTTP_401_UNAUTHORIZED,
            )
        if isinstance(exc, NotFound):
            return _respuesta(
                _mensaje_o_defecto(
                    exc,
                    "No se encontró el recurso solicitado.",
                    (_DETALLE_NO_ENCONTRADO_EN,),
                ),
                "no_encontrado",
                status.HTTP_404_NOT_FOUND,
            )
        if isinstance(exc, PermissionDenied):
            return _respuesta(
                _mensaje_o_defecto(
                    exc,
                    "No tienes permiso para realizar esta acción.",
                    (_DETALLE_SIN_PERMISO_EN,),
                ),
                "sin_permiso",
                status.HTTP_403_FORBIDDEN,
            )
        if isinstance(exc, Throttled):
            espera = None
            try:
                espera = exc.wait()
            except Exception:
                espera = None
            mensaje = "Demasiadas peticiones. Espera un momento e inténtalo de nuevo."
            if espera:
                mensaje = (
                    f"Demasiadas peticiones. Espera {int(espera)} segundos "
                    "e inténtalo de nuevo."
                )
            return _respuesta(mensaje, "demasiadas_peticiones", status.HTTP_429_TOO_MANY_REQUESTS)
        if isinstance(exc, APIException):
            # Cualquier otra excepción de DRF (405, 400 de parseo, ...):
            # mensaje fijo en español por código, sin exponer el texto
            # interno de DRF.
            mensajes_por_codigo = {
                status.HTTP_400_BAD_REQUEST: (
                    "La petición no es válida.",
                    "solicitud_invalida",
                ),
                status.HTTP_405_METHOD_NOT_ALLOWED: (
                    "Ese método no está permitido en este endpoint.",
                    "metodo_no_permitido",
                ),
                status.HTTP_406_NOT_ACCEPTABLE: (
                    "El formato pedido no está disponible.",
                    "formato_no_aceptado",
                ),
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: (
                    "El tipo de contenido enviado no está admitido.",
                    "contenido_no_admitido",
                ),
            }
            mensaje, codigo = mensajes_por_codigo.get(
                response.status_code,
                ("Ocurrió un error con la petición.", "error_api"),
            )
            return _respuesta(mensaje, codigo, response.status_code)
        return response

    # --- Cualquier otro error no previsto: 500 en JSON, nunca HTML ---
    logger.exception("Error interno no controlado en la API")
    return _respuesta(
        "Ocurrió un error interno. Revisa el registro del servidor.",
        "error_interno",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )

"""Cifrado simétrico de las credenciales guardadas en la base de datos.

Las contraseñas de los routers (``Router.password``) y de los clientes PPPoE
(``ClientePPPoE.password_pppoe``) se guardan cifradas con Fernet
(``cryptography``) cuando está configurada la variable de entorno
``MIKROTIK_CREDENTIALS_KEY``. Los valores cifrados llevan el prefijo
``"ENC1:"`` y solo se pueden descifrar con esa misma clave.

Compatibilidad con datos existentes: si la clave no está configurada, los
valores se guardan como antes (texto plano) y se registra una advertencia,
para no romper instalaciones ni tests. Los valores en texto plano ya
guardados NO se cifran solos: hay que reintroducirlos o ejecutar
``python manage.py cifrar_credenciales`` después de configurar la clave
(ver ``docs/security.md``).

La clave debe guardarse fuera del repositorio (variable de entorno o gestor
de secretos). Perderla deja inaccesibles las credenciales cifradas: no hay
forma de recuperarlas sin ella.
"""

import logging
import os

logger = logging.getLogger(__name__)

ENV_VAR = "MIKROTIK_CREDENTIALS_KEY"
PREFIX = "ENC1:"


def _load_key():
    """Devuelve la clave Fernet configurada, o ``None`` si no hay ninguna.

    La clave debe ser una clave Fernet válida (base64 urlsafe de 32 bytes),
    generada por ejemplo con ``Fernet.generate_key()``.
    """
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        return None
    try:
        from cryptography.fernet import Fernet

        Fernet(raw.encode("ascii"))
    except Exception as exc:  # clave mal formada o cryptography no instalado
        raise ValueError(
            f"La variable de entorno {ENV_VAR} no contiene una clave Fernet "
            f"válida. Genera una con: python -c \"from cryptography.fernet "
            f"import Fernet; print(Fernet.generate_key().decode())\""
        ) from exc
    return raw.encode("ascii")


def encryption_configured():
    """True si hay una clave de cifrado válida configurada."""
    return _load_key() is not None


def encrypt_value(value):
    """Cifra ``value`` si hay clave configurada; si no, lo devuelve tal cual.

    Los valores ya cifrados (con el prefijo ``ENC1:``) se devuelven sin
    cambios, para no cifrar dos veces al guardar un objeto existente.
    """
    if not value:
        return value
    if value.startswith(PREFIX):
        return value
    key = _load_key()
    if key is None:
        logger.warning(
            "MIKROTIK_CREDENTIALS_KEY no está configurada: la credencial se "
            "guarda en texto plano. Configura la clave y ejecuta "
            "'python manage.py cifrar_credenciales'."
        )
        return value
    from cryptography.fernet import Fernet

    return PREFIX + Fernet(key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_value(value):
    """Descifra un valor guardado por :func:`encrypt_value`.

    Los valores sin el prefijo ``ENC1:`` son credenciales antiguas en texto
    plano y se devuelven tal cual (compatibilidad hacia atrás). Si el valor
    está cifrado y no hay clave configurada (o es otra clave), se lanza
    ``ValueError``: sin la clave correcta los datos son inaccesibles.
    """
    if not value or not value.startswith(PREFIX):
        return value
    key = _load_key()
    if key is None:
        raise ValueError(
            f"La credencial está cifrada pero {ENV_VAR} no está configurada. "
            "Configura la misma clave con la que se cifró para poder usarla."
        )
    from cryptography.fernet import Fernet, InvalidToken

    try:
        return Fernet(key).decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(
            f"La credencial no se pudo descifrar con {ENV_VAR}: la clave no "
            "es la misma con la que se cifró."
        ) from exc


def generate_key():
    """Genera una clave Fernet nueva (para documentar su creación)."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode("ascii")

# api_mikrotik/exceptions.py
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

class MikroTikError(Exception):
    """Excepción base para errores relacionados con la API de MikroTik."""
    def __init__(self, message="Ocurrió un error en el MikroTik"):
        self.message = message
        super().__init__(self.message)

class MikroTikConnectionError(MikroTikError):
    """Se lanza cuando no se puede establecer comunicación con el router."""
    pass


def custom_exception_handler(exc, context):
    """
    Manejador global para interceptar errores de MikroTik en toda la API
    sin tener que poner try...except en los ViewSets.
    """
    # Primero dejamos que DRF maneje sus excepciones estándar (ValidationError, NotFound, etc.)
    response = exception_handler(exc, context)

    # Si la excepción que ocurrió es hija de nuestro MikroTikError...
    if isinstance(exc, MikroTikError):
        return Response(
            {"mikrotik_error": exc.message},
            status=status.HTTP_502_BAD_GATEWAY
        )

    return response
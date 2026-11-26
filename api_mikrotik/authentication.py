"""Autenticación por token con expiración opcional.

Igual que ``TokenAuthentication`` de DRF, pero si está configurado
``DJANGO_TOKEN_EXPIRY_DAYS`` (en días, 0 = desactivado, que es el valor por
defecto), los tokens más viejos que ese plazo dejan de valer: se eliminan
y hay que pedir uno nuevo con ``POST /api/token/``.

Por defecto la expiración está desactivada para no romper el uso actual
(la web guarda el token en sesión y Adrián lo usa en local). La revocación
manual está disponible siempre en ``POST /api/token/revocar/``.
Ver ``docs/security.md``.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class TokenExpirableAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        dias = int(getattr(settings, 'TOKEN_EXPIRY_DAYS', 0) or 0)
        if dias > 0 and token.created < timezone.now() - timedelta(days=dias):
            token.delete()
            raise AuthenticationFailed(
                'El token caducó. Pide uno nuevo con POST /api/token/.'
            )
        return user, token

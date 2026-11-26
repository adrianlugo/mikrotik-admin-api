from django.contrib.auth import logout
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema


@extend_schema(summary="Obtener token de acceso", tags=['Autenticación'])
class ObtenerTokenView(ObtainAuthToken):
    permission_classes = [AllowAny]


class RevocarTokenResponseSerializer(serializers.Serializer):
    detail = serializers.CharField(read_only=True)


@extend_schema(
    summary="Revocar el token de acceso (cerrar sesión)",
    description=(
        "Elimina el token DRF del usuario autenticado y cierra su sesión. "
        "Después de revocarlo hay que pedir uno nuevo con POST /api/token/. "
        "Antes no había forma de cerrar sesión: el token seguía valiendo "
        "aunque se cerrara la sesión en la web. La expiración automática "
        "sigue siendo opcional (DJANGO_TOKEN_EXPIRY_DAYS, ver docs/security.md)."
    ),
    tags=['Autenticación'],
)
class RevocarTokenView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RevocarTokenResponseSerializer

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        logout(request)
        return Response(
            {"detail": "Token revocado. Pide uno nuevo con POST /api/token/."},
            status=status.HTTP_200_OK,
        )

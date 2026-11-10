from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema


@extend_schema(summary="Obtener token de acceso", tags=['Autenticación'])
class ObtenerTokenView(ObtainAuthToken):
    permission_classes = [AllowAny]
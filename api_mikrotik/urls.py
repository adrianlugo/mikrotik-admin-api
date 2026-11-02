from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from .views import ClientePPPoEViewSet, ClienteRedViewSet, FacturaViewSet, PagoViewSet, PlanVelocidadViewSet, RouterViewSet, portal_cliente

# El router de REST Framework genera las rutas automáticas
router = DefaultRouter()
router.register(r'routers', RouterViewSet, basename='router')
router.register(r'clientes-pppoe', ClientePPPoEViewSet, basename='cliente-pppoe')
router.register(r'clientes-red', ClienteRedViewSet, basename='cliente-red')
router.register(r'planes', PlanVelocidadViewSet, basename='plan')
router.register(r'facturas', FacturaViewSet, basename='factura')
router.register(r'pagos', PagoViewSet, basename='pago')

urlpatterns = [
    path('token/', obtain_auth_token, name='api-token'),
    path('portal/<str:token>/', portal_cliente, name='portal-cliente'),
    path('', include(router.urls)),
]

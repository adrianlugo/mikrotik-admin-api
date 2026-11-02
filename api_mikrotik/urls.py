from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClientePPPoEViewSet, ClienteRedViewSet, FacturaViewSet, ObtenerTokenView, PagoViewSet, PlanVelocidadViewSet, RouterViewSet, portal_cliente

# El router de REST Framework genera las rutas automáticas
router = DefaultRouter()
router.register(r'routers', RouterViewSet, basename='router')
router.register(r'clientes-pppoe', ClientePPPoEViewSet, basename='cliente-pppoe')
router.register(r'clientes-red', ClienteRedViewSet, basename='cliente-red')
router.register(r'planes', PlanVelocidadViewSet, basename='plan')
router.register(r'facturas', FacturaViewSet, basename='factura')
router.register(r'pagos', PagoViewSet, basename='pago')

urlpatterns = [
    path('token/', ObtenerTokenView.as_view(), name='api-token'),
    path('portal/<str:token>/', portal_cliente, name='portal-cliente'),
    path('', include(router.urls)),
]

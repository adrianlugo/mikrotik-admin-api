from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClientePPPoEViewSet, PlanVelocidadViewSet, RouterViewSet

# El router de REST Framework genera las rutas automáticas
router = DefaultRouter()
router.register(r'routers', RouterViewSet, basename='router')
router.register(r'clientes-pppoe', ClientePPPoEViewSet, basename='cliente-pppoe')
router.register(r'planes', PlanVelocidadViewSet, basename='plan')

urlpatterns = [
    path('', include(router.urls)),
]

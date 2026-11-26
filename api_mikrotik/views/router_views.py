from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, extend_schema_view

from api_mikrotik.models import Router, ClientePPPoE, ClienteRed, PlanVelocidad
from api_mikrotik.serializers import RouterSerializer
from api_mikrotik.services import MikroTikBaseService, PPPoEService, NetworkClientService, TrafficService
from api_mikrotik.permissions import PermisoOperativo


@extend_schema_view(
    list=extend_schema(summary="Listar routers", tags=['Routers MikroTik']),
    retrieve=extend_schema(summary="Obtener un router", tags=['Routers MikroTik']),
    create=extend_schema(summary="Registrar un router", tags=['Routers MikroTik']),
    update=extend_schema(summary="Actualizar un router", tags=['Routers MikroTik']),
    partial_update=extend_schema(summary="Actualizar parcialmente un router", tags=['Routers MikroTik']),
    destroy=extend_schema(summary="Eliminar un router", tags=['Routers MikroTik']),
)
class RouterViewSet(viewsets.ModelViewSet):
    queryset = Router.objects.all()
    serializer_class = RouterSerializer
    permission_classes = [PermisoOperativo]

    @extend_schema(summary="Verificar conexión del router", tags=['Routers MikroTik'])
    @action(detail=True, methods=['post'], url_path='verificar-conexion')
    def verificar_conexion(self, request, pk=None):
        router = self.get_object()
        resultado = MikroTikBaseService(router).verificar_conexion()
        return Response(resultado, status=status.HTTP_200_OK)

    @extend_schema(summary="Sincronizar este router", tags=['Routers MikroTik'])
    @action(detail=True, methods=['post'], url_path='sincronizar')
    def sincronizar(self, request, pk=None):
        router = self.get_object()
        resultado = PPPoEService(router).sincronizar_bidireccional()
        status_code = status.HTTP_200_OK if resultado['status'] == 'success' else status.HTTP_502_BAD_GATEWAY
        return Response(resultado, status=status_code)

    @extend_schema(summary="Consultar estado del router", tags=['Routers MikroTik'])
    @action(detail=True, methods=['get'], url_path='estado')
    def estado(self, request, pk=None):
        router = self.get_object()
        conexion = MikroTikBaseService(router).verificar_conexion()
        return Response({
            'router': router.nombre,
            'activo': router.activo,
            'conexion': conexion,
            'clientes_configurados': ClientePPPoE.objects.filter(router=router).count(),
            'clientes_red_configurados': ClienteRed.objects.filter(router=router).count(),
            'planes_configurados': PlanVelocidad.objects.filter(router=router).count(),
        }, status=status.HTTP_200_OK)

    @extend_schema(summary="Monitorear consumo del router", tags=['Monitoreo MikroTik'])
    @action(detail=True, methods=['get'], url_path='consumo')
    def consumo(self, request, pk=None):
        router = self.get_object()
        colas = TrafficService(router).monitor_consumo()
        return Response({'router': router.nombre, 'total_colas': len(colas), 'colas': colas})

    @extend_schema(summary="Crear y reparar colas de clientes", tags=['Routers MikroTik'])
    @action(detail=True, methods=['post'], url_path='reparar-colas')
    def reparar_colas(self, request, pk=None):
        router = self.get_object()
        resultado = NetworkClientService(router).reparar_usuarios_red()
        code = status.HTTP_200_OK if resultado.get('status') == 'success' else status.HTTP_502_BAD_GATEWAY
        return Response(resultado, status=code)

    @extend_schema(summary="Listar leases DHCP", tags=['Monitoreo MikroTik'])
    @action(detail=True, methods=['get'], url_path='dhcp-leases')
    def dhcp_leases(self, request, pk=None):
        router = self.get_object()
        leases = NetworkClientService(router).listar_dhcp_leases()
        return Response({'router': router.nombre, 'total': len(leases), 'leases': leases})

    @extend_schema(summary="Listar direcciones IP del router para el local-address", tags=['Routers MikroTik'])
    @action(detail=True, methods=['get'], url_path='direcciones-ip')
    def direcciones_ip(self, request, pk=None):
        """Desplegable de local-address al crear o editar un plan.

        Devuelve las direcciones de /ip/address de este router con su
        interfaz. La web muestra interfaz + IP (por ejemplo el loopback),
        pero guarda solo la IP en PlanVelocidad.direccion_local, que es lo
        que pide el campo local-address del perfil PPPoE.
        """
        router = self.get_object()
        direcciones = PPPoEService(router).listar_direcciones_ip()
        return Response({'router': router.nombre, 'total': len(direcciones), 'direcciones': direcciones})

    @extend_schema(summary="Listar pools del router para el remote-address", tags=['Routers MikroTik'])
    @action(detail=True, methods=['get'], url_path='pools')
    def pools(self, request, pk=None):
        """Desplegable de remote-address al crear o editar un plan.

        Devuelve los pools de /ip/pool de este router con su nombre y sus
        rangos. La web guarda el nombre del pool elegido en
        PlanVelocidad.pool_remoto.
        """
        router = self.get_object()
        pools = PPPoEService(router).listar_pools()
        return Response({'router': router.nombre, 'total': len(pools), 'pools': pools})

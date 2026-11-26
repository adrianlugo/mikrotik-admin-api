from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, extend_schema_view

from api_mikrotik.exceptions import MikroTikConnectionError
from api_mikrotik.models import Router, ClientePPPoE, ClienteRed, PlanVelocidad
from api_mikrotik.serializers import RouterSerializer
from api_mikrotik.services import MikroTikBaseService, PPPoEService, NetworkClientService, TrafficService
from api_mikrotik.permissions import PermisoOperativo


def _error_router_502(exc):
    """Respuesta 502 honesta cuando el router no responde.

    Antes varios endpoints devolvían 200 con listas vacías o con 0, como si
    el router no tuviera datos. Ahora un fallo de comunicación es un error.
    """
    return Response(
        {"error": "No se pudo comunicar con el router.", "detalle": str(exc)},
        status=status.HTTP_502_BAD_GATEWAY,
    )


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
        # Antes siempre devolvía 200, incluso cuando la conexión fallaba.
        codigo = status.HTTP_200_OK if resultado.get('status') == 'success' else status.HTTP_502_BAD_GATEWAY
        return Response(resultado, status=codigo)

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
        codigo = status.HTTP_200_OK if conexion.get('status') == 'success' else status.HTTP_502_BAD_GATEWAY
        return Response({
            'router': router.nombre,
            'activo': router.activo,
            'conexion': conexion,
            'clientes_configurados': ClientePPPoE.objects.filter(router=router).count(),
            'clientes_red_configurados': ClienteRed.objects.filter(router=router).count(),
            'planes_configurados': PlanVelocidad.objects.filter(router=router).count(),
        }, status=codigo)

    @extend_schema(summary="Monitorear consumo del router", tags=['Monitoreo MikroTik'])
    @action(detail=True, methods=['get'], url_path='consumo')
    def consumo(self, request, pk=None):
        router = self.get_object()
        try:
            colas = TrafficService(router).monitor_consumo()
        except MikroTikConnectionError as exc:
            return _error_router_502(exc)
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
        try:
            leases = NetworkClientService(router).listar_dhcp_leases()
        except MikroTikConnectionError as exc:
            return _error_router_502(exc)
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
        try:
            direcciones = PPPoEService(router).listar_direcciones_ip()
        except MikroTikConnectionError as exc:
            return _error_router_502(exc)
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
        try:
            pools = PPPoEService(router).listar_pools()
        except MikroTikConnectionError as exc:
            return _error_router_502(exc)
        return Response({'router': router.nombre, 'total': len(pools), 'pools': pools})

    @extend_schema(summary="Listar colas simples del router para la cola padre", tags=['Routers MikroTik'])
    @action(detail=True, methods=['get'], url_path='colas')
    def colas(self, request, pk=None):
        """Desplegable de cola padre al crear o editar un plan.

        Devuelve las colas simples de /queue/simple de este router con su
        nombre, target, max-limit y parent. La web muestra nombre +
        max-limit/target y guarda solo el nombre en
        PlanVelocidad.cola_padre. Si no se elige ninguna, el plan queda
        sin cola padre (none): la API ya no genera una cola
        Plan-{nombre_perfil} (ver docs/api.md).
        """
        router = self.get_object()
        try:
            colas = TrafficService(router).listar_colas_resumen()
        except MikroTikConnectionError as exc:
            return _error_router_502(exc)
        return Response({'router': router.nombre, 'total': len(colas), 'colas': colas})

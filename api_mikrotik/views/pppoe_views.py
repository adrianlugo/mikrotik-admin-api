from django.db import transaction
from rest_framework import viewsets, status, serializers
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from drf_spectacular.utils import extend_schema, inline_serializer, extend_schema_view

from api_mikrotik.models import ClientePPPoE, Router
from api_mikrotik.serializers import ClientePPPoESerializer
from api_mikrotik.services import MikroTikBaseService, PPPoEService
from api_mikrotik.permissions import PermisoOperativo


@extend_schema_view(
    list=extend_schema(
        summary="Listar todos los clientes PPPoE",
        description="Retorna la lista completa de clientes registrados en Django. Permite filtrar por estado, router y plan, o buscar por nombre.",
        tags=['Clientes PPPoE']
    ),
    create=extend_schema(
        summary="Crear un nuevo cliente PPPoE",
        description="Registra al usuario en la base de datos local y, en simultáneo, lo da de alta de forma automática en el MikroTik configurado.",
        tags=['Clientes PPPoE']
    ),
    retrieve=extend_schema(
        summary="Obtener detalles de un cliente",
        description="Recupera la información completa de un perfil de cliente PPPoE específico mediante su ID único.",
        tags=['Clientes PPPoE']
    ),
    update=extend_schema(
        summary="Actualizar cliente por completo",
        description="Modifica todos los campos de un cliente (ej. cambio de credenciales o perfil de velocidad) e impacta los cambios inmediatamente en el MikroTik.",
        tags=['Clientes PPPoE']
    ),
    partial_update=extend_schema(
        summary="Actualizar campos específicos del cliente",
        description="Permite realizar modificaciones parciales (ej. modificar solo la contraseña) sin necesidad de enviar todo el formulario.",
        tags=['Clientes PPPoE']
    ),
    destroy=extend_schema(
        summary="Eliminar un cliente del sistema",
        description="Remueve el secreto PPPoE del router MikroTik en tiempo real y, posteriormente, elimina de forma permanente el registro en Django.",
        tags=['Clientes PPPoE']
    ),
)
class ClientePPPoEViewSet(viewsets.ModelViewSet):
    queryset = ClientePPPoE.objects.select_related('router', 'plan').all()
    serializer_class = ClientePPPoESerializer
    permission_classes = [PermisoOperativo]
    permite_tecnico_edicion = True
    
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['estado', 'router', 'plan']
    search_fields = ['usuario_pppoe', 'nombre_completo']

    @extend_schema(
        summary="Listar usuarios activos en MikroTik",
        description="Consulta en el router asociado al conjunto de clientes las sesiones PPP activas reportadas por RouterOS.",
        responses={200: inline_serializer(
            name='UsuariosActivosResponse',
            fields={
                'routers': serializers.ListField(child=serializers.CharField()),
                'total_conectados': serializers.IntegerField(),
                'conexiones': serializers.ListField(child=serializers.CharField()),
                'errores': serializers.ListField(child=serializers.DictField())
            }
        )},
        tags=['Monitoreo MikroTik']
    )
    @action(detail=False, methods=['get'], url_path='activos')
    def listar_activos(self, request):
        usuarios_activos = []
        routers_consultados = []
        errores = []
        router_ids = ClientePPPoE.objects.values_list('router_id', flat=True)
        for router in Router.objects.filter(pk__in=router_ids).distinct():
            resultado = PPPoEService(router).obtener_conexiones_activas()
            routers_consultados.append(router.nombre)
            if isinstance(resultado, list):
                usuarios_activos.extend(resultado)
            else:
                errores.append({"router": router.nombre, "mensaje": resultado.get("message", "No fue posible consultar las sesiones")})

        if not routers_consultados:
            return Response({"error": "No hay clientes PPPoE asociados a routers registrados"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "routers": routers_consultados,
            "total_conectados": len(usuarios_activos),
            "conexiones": usuarios_activos,
            "errores": errores
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            cliente = serializer.save()
            router = cliente.router
            plan = cliente.plan
            
            mikrotik_service = PPPoEService(router)
            resultado = mikrotik_service.crear_usuario_pppoe(
                usuario=cliente.usuario_pppoe,
                password=cliente.password_pppoe,
                plan_perfil=plan.nombre_perfil
            )
            
            if resultado.get("status") == "error":
                raise serializers.ValidationError({"mikrotik_error": resultado.get("message")})
        
        headers = self.get_success_headers(serializer.data)
        return Response({
            "cliente": serializer.data,
            "mikrotik_status": resultado
        }, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        cliente = self.get_object()
        usuario_antiguo = cliente.usuario_pppoe
        
        serializer = self.get_serializer(cliente, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            cliente_actualizado = serializer.save()
            
            mikrotik_service = PPPoEService(cliente_actualizado.router)
            resultado = mikrotik_service.actualizar_usuario_pppoe(
                usuario_antiguo=usuario_antiguo,
                nuevo_usuario=cliente_actualizado.usuario_pppoe,
                nuevo_password=cliente_actualizado.password_pppoe,
                nuevo_plan_perfil=cliente_actualizado.plan.nombre_perfil
            )
            
            if resultado.get("status") == "error":
                raise serializers.ValidationError({"mikrotik_error": resultado.get("message")})
                
        return Response({
            "cliente": serializer.data,
            "mikrotik_status": resultado
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        cliente = self.get_object()
        usuario_pppoe = cliente.usuario_pppoe
        router = cliente.router
        
        with transaction.atomic():
            mikrotik_service = PPPoEService(router)
            resultado = mikrotik_service.eliminar_usuario_pppoe(usuario_pppoe)
            
            if resultado.get("status") == "error":
                return Response({"mikrotik_error": resultado.get("message")}, status=status.HTTP_502_BAD_GATEWAY)
            
            cliente.delete()
            
        return Response({
            "message": "Cliente eliminado localmente y del MikroTik",
            "mikrotik_status": resultado
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Cambiar estado del cliente (Suspender/Reactivar)",
        request=inline_serializer(
            name='CambiarEstadoRequest',
            fields={'estado': serializers.ChoiceField(choices=['activo', 'suspendido'])}
        ),
        tags=['Clientes PPPoE']
    )
    @action(detail=True, methods=['post'], url_path='cambiar-estado')
    def cambiar_estado(self, request, pk=None):
        cliente = self.get_object()
        nuevo_estado = request.data.get('estado')
        
        if nuevo_estado not in ['activo', 'suspendido']:
            return Response({"error": "Estado inválido. Use 'activo' o 'suspendido'."}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            cliente.estado = nuevo_estado
            cliente.save()
            
            mikrotik_service = PPPoEService(cliente.router)
            
            if nuevo_estado == 'suspendido':
                resultado = mikrotik_service.suspender_usuario_pppoe(
                    usuario_pppoe=cliente.usuario_pppoe,
                    perfil_corte="Perfil_Corte"
                )
            else:
                resultado = mikrotik_service.actualizar_usuario_pppoe(
                    usuario_antiguo=cliente.usuario_pppoe,
                    nuevo_usuario=cliente.usuario_pppoe,
                    nuevo_password=cliente.password_pppoe,
                    nuevo_plan_perfil=cliente.plan.nombre_perfil
                )
                
            if resultado.get("status") == "error":
                raise serializers.ValidationError({"mikrotik_error": resultado.get("message")})
            
        return Response({
            "message": f"Estado del cliente actualizado a {nuevo_estado}",
            "mikrotik_status": resultado,
            "cliente_estado": cliente.estado
        }, status=status.HTTP_200_OK)

    @extend_schema(summary="Hacer ping desde el router al equipo del cliente", tags=['Monitoreo MikroTik'])
    @action(detail=True, methods=['post'], url_path='ping')
    def ping(self, request, pk=None):
        cliente = self.get_object()
        destino = request.data.get('ip', cliente.direccion_ip_antena)
        if not destino:
            return Response({"error": "Configure direccion_ip_antena o envíe ip en el cuerpo."}, status=status.HTTP_400_BAD_REQUEST)
        resultado = MikroTikBaseService(cliente.router).ping_desde_router(destino)
        codigo = status.HTTP_200_OK if resultado['status'] == 'success' else status.HTTP_502_BAD_GATEWAY
        return Response(resultado, status=codigo)

    @extend_schema(summary="Desconectar sesión PPPoE activa", tags=['Monitoreo MikroTik'])
    @action(detail=True, methods=['post'], url_path='patear')
    def patear(self, request, pk=None):
        cliente = self.get_object()
        resultado = PPPoEService(cliente.router).patear_usuario_pppoe(cliente.usuario_pppoe)
        codigo = status.HTTP_200_OK if resultado['status'] == 'success' else status.HTTP_502_BAD_GATEWAY
        return Response(resultado, status=codigo)


@extend_schema(
    summary="Consultar estado público del cliente",
    responses={200: inline_serializer(name='PortalClienteResponse', fields={'cliente': serializers.CharField(), 'estado': serializers.CharField(), 'servicio': serializers.CharField(), 'mensaje': serializers.CharField()}), 404: None},
    auth=[],
    tags=['Portal de clientes'],
)
@api_view(['GET'])
@permission_classes([AllowAny])
def portal_cliente(request, token):
    try:
        cliente = ClientePPPoE.objects.select_related('plan').get(portal_token=token)
    except (ClientePPPoE.DoesNotExist, ValueError, TypeError):
        return Response({'detail': 'Enlace de cliente inválido.'}, status=status.HTTP_404_NOT_FOUND)
    return Response({
        'cliente': cliente.nombre_completo,
        'estado': cliente.estado,
        'servicio': cliente.plan.nombre_perfil,
        'mensaje': 'Su servicio está suspendido por falta de pago.' if cliente.estado == 'suspendido' else 'Su servicio se encuentra activo.',
    })
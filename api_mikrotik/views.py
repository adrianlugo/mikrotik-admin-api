from django.db import transaction
from rest_framework import viewsets, status, serializers
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from drf_spectacular.utils import extend_schema, inline_serializer, extend_schema_view

from .models import ClientePPPoE, ClienteRed, PlanVelocidad, Router
from .serializers import ClientePPPoESerializer, ClienteRedSerializer, PlanVelocidadSerializer, RouterSerializer
from .services import MikroTikService

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
    queryset = ClientePPPoE.objects.all()
    serializer_class = ClientePPPoESerializer
    
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['estado', 'router', 'plan']
    search_fields = ['usuario_pppoe', 'nombre_completo']

    @extend_schema(
        summary="Listar usuarios activos en MikroTik",
        description="Consulta mediante la API del MikroTik las conexiones activas en tiempo real del primer router configurado.",
        responses={200: inline_serializer(
            name='UsuariosActivosResponse',
            fields={
                'router': serializers.CharField(),
                'total_conectados': serializers.IntegerField(),
                'conexiones': serializers.ListField(child=serializers.CharField())
            }
        )},
        tags=['Monitoreo MikroTik']
    )
    @action(detail=False, methods=['get'], url_path='activos')
    def listar_activos(self, request):
        """Endpoint para consultar el estado en tiempo real del MikroTik"""
        router_principal = Router.objects.first()
        
        if not router_principal:
            return Response({"error": "No hay ningún router registrado en el sistema"}, status=status.HTTP_400_BAD_REQUEST)
        
        mikrotik_service = MikroTikService(router_principal)
        usuarios_activos = mikrotik_service.obtener_conexiones_activas()
        
        return Response({
            "router": router_principal.nombre,
            "total_conectados": len(usuarios_activos),
            "conexiones": usuarios_activos
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Envolvemos la creación en un bloque atómico. Si algo falla adentro, la BD vuelve atrás.
        with transaction.atomic():
            cliente = serializer.save()
            
            router = cliente.router
            plan = cliente.plan
            
            mikrotik_service = MikroTikService(router)
            resultado = mikrotik_service.crear_usuario_pppoe(
                usuario=cliente.usuario_pppoe,
                password=cliente.password_pppoe,
                plan_perfil=plan.nombre_perfil
            )
            
            # Si el servicio MikroTik reportó un problema de conexión o credenciales:
            if resultado.get("status") == "error":
                # Forzamos una excepción para cancelar el guardado en la base de datos de Django
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
            
            mikrotik_service = MikroTikService(cliente_actualizado.router)
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
            mikrotik_service = MikroTikService(router)
            resultado = mikrotik_service.eliminar_usuario_pppoe(usuario_pppoe)
            
            # Si no se pudo borrar del MikroTik, no lo borramos de Django para no perder el rastro del cliente.
            if resultado.get("status") == "error":
                return Response({"mikrotik_error": resultado.get("message")}, status=status.HTTP_502_BAD_GATEWAY)
            
            cliente.delete()
            
        return Response({
            "message": "Cliente eliminado localmente y del MikroTik",
            "mikrotik_status": resultado
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Cambiar estado del cliente (Suspender/Reactivar)",
        description="Modifica el estado manual de un usuario PPPoE en Django y altera su perfil en el MikroTik (lo mueve al perfil de corte o le devuelve su plan contratado).",
        request=inline_serializer(
            name='CambiarEstadoRequest',
            fields={'estado': serializers.ChoiceField(choices=['activo', 'suspendido'])}
        ),
        responses={200: inline_serializer(
            name='CambiarEstadoResponse',
            fields={
                'message': serializers.CharField(),
                'mikrotik_status': serializers.CharField(),
                'cliente_estado': serializers.CharField()
            }
        )},
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
            
            mikrotik_service = MikroTikService(cliente.router)
            
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

@extend_schema_view(
    list=extend_schema(summary="Listar routers", description="Obtiene los routers MikroTik configurados en la API.", tags=['Routers MikroTik']),
    retrieve=extend_schema(summary="Obtener un router", description="Obtiene los datos de configuración de un router específico.", tags=['Routers MikroTik']),
    create=extend_schema(summary="Registrar un router", description="Registra la dirección, credenciales y puerto API de un router.", tags=['Routers MikroTik']),
    update=extend_schema(summary="Actualizar un router", description="Reemplaza la configuración completa de un router.", tags=['Routers MikroTik']),
    partial_update=extend_schema(summary="Actualizar parcialmente un router", description="Modifica únicamente los campos enviados de un router.", tags=['Routers MikroTik']),
    destroy=extend_schema(summary="Eliminar un router", description="Elimina la configuración local de un router si no tiene datos protegidos asociados.", tags=['Routers MikroTik']),
)
class RouterViewSet(viewsets.ModelViewSet):
    queryset = Router.objects.all()
    serializer_class = RouterSerializer

    @extend_schema(summary="Verificar conexión del router", description="Abre una conexión API, consulta recursos básicos y devuelve identidad, versión y uptime del MikroTik.", tags=['Routers MikroTik'])
    @action(detail=True, methods=['post'], url_path='verificar-conexion')
    def verificar_conexion(self, request, pk=None):
        router = self.get_object()
        resultado = MikroTikService(router).verificar_conexion()
        status_code = status.HTTP_200_OK if resultado['status'] == 'success' else status.HTTP_502_BAD_GATEWAY
        return Response(resultado, status=status_code)

    @extend_schema(summary="Sincronizar este router", description="Crea o actualiza en ambos sentidos los profiles, planes, secretos PPPoE y clientes asociados a este router.", tags=['Routers MikroTik'])
    @action(detail=True, methods=['post'], url_path='sincronizar')
    def sincronizar(self, request, pk=None):
        router = self.get_object()
        resultado = MikroTikService(router).sincronizar_bidireccional()
        status_code = status.HTTP_200_OK if resultado['status'] == 'success' else status.HTTP_502_BAD_GATEWAY
        return Response(resultado, status=status_code)

    @extend_schema(summary="Consultar estado del router", description="Devuelve configuración local, resultado de conexión y cantidades de planes y clientes asociados.", tags=['Routers MikroTik'])
    @action(detail=True, methods=['get'], url_path='estado')
    def estado(self, request, pk=None):
        router = self.get_object()
        conexion = MikroTikService(router).verificar_conexion()
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
        colas = MikroTikService(router).monitor_consumo()
        return Response({'router': router.nombre, 'total_colas': len(colas), 'colas': colas})

    @extend_schema(summary="Crear y reparar colas de clientes", tags=['Routers MikroTik'])
    @action(detail=True, methods=['post'], url_path='reparar-colas')
    def reparar_colas(self, request, pk=None):
        router = self.get_object()
        resultado = MikroTikService(router).reparar_usuarios_red()
        code = status.HTTP_200_OK if resultado.get('status') == 'success' else status.HTTP_502_BAD_GATEWAY
        return Response(resultado, status=code)

    @extend_schema(summary="Listar leases DHCP", tags=['Monitoreo MikroTik'])
    @action(detail=True, methods=['get'], url_path='dhcp-leases')
    def dhcp_leases(self, request, pk=None):
        router = self.get_object()
        leases = MikroTikService(router).listar_dhcp_leases()
        return Response({'router': router.nombre, 'total': len(leases), 'leases': leases})


@extend_schema_view(
    list=extend_schema(
        summary="Listar planes de velocidad",
        description="Obtiene los planes locales con sus velocidades de subida, bajada, profile PPP y router asociado.",
        tags=['Planes de velocidad'],
    ),
    retrieve=extend_schema(
        summary="Consultar un plan de velocidad",
        description="Obtiene toda la información de un plan específico mediante su identificador.",
        tags=['Planes de velocidad'],
    ),
    create=extend_schema(
        summary="Crear un plan de velocidad",
        description="Guarda el plan en Django y crea o actualiza el profile correspondiente en su router MikroTik.",
        tags=['Planes de velocidad'],
    ),
    update=extend_schema(
        summary="Actualizar completamente un plan",
        description="Reemplaza todos los datos editables del plan y lo mantiene alineado con la configuración local.",
        tags=['Planes de velocidad'],
    ),
    partial_update=extend_schema(
        summary="Actualizar parcialmente un plan",
        description="Modifica únicamente los campos enviados; por ejemplo, la velocidad de subida o bajada.",
        tags=['Planes de velocidad'],
    ),
    destroy=extend_schema(
        summary="Eliminar un plan de velocidad",
        description="Elimina el plan local cuando ningún cliente protegido lo utiliza.",
        tags=['Planes de velocidad'],
    ),
)
class PlanVelocidadViewSet(viewsets.ModelViewSet):
    queryset = PlanVelocidad.objects.all()
    serializer_class = PlanVelocidadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            plan = serializer.save()
            mikrotik_service = MikroTikService(plan.router)
            if not plan.cola_padre:
                plan.cola_padre = f"Plan-{plan.nombre_perfil}"
                plan.save(update_fields=['cola_padre'])
            resultado = mikrotik_service.crear_perfil_velocidad(
                nombre_perfil=plan.nombre_perfil,
                subida=f"{plan.subida_mbps}M",
                bajada=f"{plan.bajada_mbps}M",
                cola_padre=plan.cola_padre,
            )
            resultado_cola = mikrotik_service.asegurar_cola_padre(
                plan.cola_padre, plan.subida_mbps, plan.bajada_mbps
            )
            if resultado.get("status") == "error":
                raise serializers.ValidationError({"mikrotik_error": resultado.get("message")})
            if resultado_cola.get("status") == "error":
                raise serializers.ValidationError({"mikrotik_error": resultado_cola.get("message")})

        headers = self.get_success_headers(serializer.data)
        return Response({
            "plan": PlanVelocidadSerializer(plan).data,
            "mikrotik_status": resultado,
            "cola_padre_status": resultado_cola,
        }, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        parcial = kwargs.get('partial', False)
        plan = self.get_object()
        serializer = self.get_serializer(plan, data=request.data, partial=parcial)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            plan = serializer.save()
            if not plan.cola_padre:
                plan.cola_padre = f"Plan-{plan.nombre_perfil}"
                plan.save(update_fields=['cola_padre'])
            mikrotik = MikroTikService(plan.router)
            perfil = mikrotik.crear_perfil_velocidad(plan.nombre_perfil, f"{plan.subida_mbps}M", f"{plan.bajada_mbps}M", plan.cola_padre)
            cola = mikrotik.asegurar_cola_padre(plan.cola_padre, plan.subida_mbps, plan.bajada_mbps)
            if perfil.get('status') == 'error':
                raise serializers.ValidationError({"mikrotik_error": perfil.get('message')})
            if cola.get('status') == 'error':
                raise serializers.ValidationError({"mikrotik_error": cola.get('message')})
        return Response({"plan": PlanVelocidadSerializer(plan).data, "mikrotik_status": perfil, "cola_padre_status": cola})


@extend_schema(tags=['Clientes DHCP e IP fija'])
class ClienteRedViewSet(viewsets.ModelViewSet):
    queryset = ClienteRed.objects.select_related('router', 'plan').all()
    serializer_class = ClienteRedSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['estado', 'router', 'plan', 'tipo']
    search_fields = ['nombre', 'direccion_ip', 'direccion_mac']

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cliente = serializer.save()
        resultado = MikroTikService(cliente.router).sincronizar_cola_cliente_red(cliente)
        if resultado.get('status') == 'error':
            cliente.delete()
            return Response({"mikrotik_error": resultado.get('message')}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"cliente": serializer.data, "mikrotik_status": resultado}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        cliente = self.get_object()
        serializer = self.get_serializer(cliente, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        cliente = serializer.save()
        resultado = MikroTikService(cliente.router).sincronizar_cola_cliente_red(cliente)
        if resultado.get('status') == 'error':
            return Response({"mikrotik_error": resultado.get('message')}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"cliente": ClienteRedSerializer(cliente).data, "mikrotik_status": resultado})

    def destroy(self, request, *args, **kwargs):
        cliente = self.get_object()
        resultado = MikroTikService(cliente.router).eliminar_cola_cliente_red(cliente)
        if resultado.get('status') == 'error':
            return Response({"mikrotik_error": resultado.get('message')}, status=status.HTTP_502_BAD_GATEWAY)
        cliente.delete()
        return Response({"message": "Cliente y cola eliminados", "mikrotik_status": resultado})

    @extend_schema(summary="Crear o reparar la cola del cliente", tags=['Clientes DHCP e IP fija'])
    @action(detail=True, methods=['post'], url_path='crear-cola')
    def crear_cola(self, request, pk=None):
        cliente = self.get_object()
        resultado = MikroTikService(cliente.router).sincronizar_cola_cliente_red(cliente)
        code = status.HTTP_200_OK if resultado.get('status') == 'success' else status.HTTP_502_BAD_GATEWAY
        return Response(resultado, status=code)

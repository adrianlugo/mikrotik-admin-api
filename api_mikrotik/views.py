from django.utils.decorators import method_decorator
from rest_framework import viewsets, status, serializers
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from drf_spectacular.utils import extend_schema, inline_serializer, extend_schema_view

from .models import ClientePPPoE
from .serializers import ClientePPPoESerializer
from .services import MikroTikService

# 1. Agrupamos y describimos cada operación estándar de la base de datos
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
    serializer_name = ClientePPPoESerializer
    serializer_class = ClientePPPoESerializer
    # Activamos los backends de filtrado y búsqueda para esta vista
    filter_backends = [DjangoFilterBackend, SearchFilter]
    
    # Filtros exactos (coincidencia perfecta)
    filterset_fields = ['estado', 'router', 'plan']
    
    # Barra de búsqueda global (coincidencia parcial/por aproximación)
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
        # Tomamos el primer router de la base de datos para la prueba
        from .models import Router
        router_principal = Router.objects.first()
        
        if not router_principal:
            return Response({"error": "No hay ningún router registrado en el sistema"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Inicializamos el servicio y extraemos los usuarios conectados
        mikrotik_service = MikroTikService(router_principal)
        usuarios_activos = mikrotik_service.obtener_conexiones_activas()
        
        return Response({
            "router": router_principal.nombre,
            "total_conectados": len(usuarios_activos),
            "conexiones": usuarios_activos
        }, status=status.HTTP_200_OK)
    
    
    def create(self, request, *args, **kwargs):
        # 1. Validamos los datos recibidos mediante el serializador
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # 2. Guardamos temporalmente la instancia en la base de datos de Django
        cliente = serializer.save()
        
        # 3. Mandamos la instrucción al MikroTik correspondiente
        router = cliente.router
        plan = cliente.plan
        
        mikrotik_service = MikroTikService(router)
        resultado = mikrotik_service.crear_usuario_pppoe(
            usuario=cliente.usuario_pppoe,
            password=cliente.password_pppoe,
            plan_perfil=plan.nombre_perfil
        )
        
        # 4. Si falla la comunicación (en un entorno real), podríamos manejarlo aquí.
        # Por ahora devolvemos el éxito del registro junto a la respuesta del MikroTik
        headers = self.get_success_headers(serializer.data)
        respuesta_final = {
            "cliente": serializer.data,
            "mikrotik_status": resultado
        }
        return Response(respuesta_final, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        # Tomamos el cliente actual antes de cambiarlo para conocer su usuario_pppoe antiguo
        cliente = self.get_object()
        usuario_antiguo = cliente.usuario_pppoe
        # Validamos y guardamos los nuevos datos en Django
        serializer = self.get_serializer(cliente, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        cliente_actualizado = serializer.save()
        # Enviamos la actualización al MikroTik
        mikrotik_service = MikroTikService(cliente_actualizado.router)
        resultado = mikrotik_service.actualizar_usuario_pppoe(
            usuario_antiguo=usuario_antiguo,
            nuevo_usuario=cliente_actualizado.usuario_pppoe,
            nuevo_password=cliente_actualizado.password_pppoe,
            nuevo_plan_perfil=cliente_actualizado.plan.nombre_perfil
        )
        return Response({
            "cliente": serializer.data,
            "mikrotik_status": resultado
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        cliente = self.get_object()
        usuario_pppoe = cliente.usuario_pppoe
        router = cliente.router
        
        # Primero eliminamos del MikroTik
        mikrotik_service = MikroTikService(router)
        resultado = mikrotik_service.eliminar_usuario_pppoe(usuario_pppoe)
        
        # Luego lo borramos de la base de datos de Django
        cliente.delete()
        
        return Response({
            "message": "Cliente eliminado localmente",
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
        """Endpoint para suspender o reactivar un cliente manualmente"""
        cliente = self.get_object()
        nuevo_estado = request.data.get('estado') # Espera 'activo' o 'suspendido'
        
        if nuevo_estado not in ['activo', 'suspendido']:
            return Response({"error": "Estado inválido. Use 'activo' o 'suspendido'."}, status=status.HTTP_400_BAD_REQUEST)
        
        cliente.estado = nuevo_estado
        cliente.save()
        
        mikrotik_service = MikroTikService(cliente.router)
        
        if nuevo_estado == 'suspendido':
            # Asumimos que tienes un perfil en tu MikroTik llamado 'Perfil_Corte'
            # En producción, podrías guardar este nombre en el modelo Router
            resultado = mikrotik_service.suspender_usuario_pppoe(
                usuario_pppoe=cliente.usuario_pppoe,
                perfil_corte="Perfil_Corte"
            )
        else:
            # Si se reactiva, le volvemos a poner su plan de velocidad original
            resultado = mikrotik_service.actualizar_usuario_pppoe(
                usuario_antiguo=cliente.usuario_pppoe,
                nuevo_usuario=cliente.usuario_pppoe,
                nuevo_password=cliente.password_pppoe,
                nuevo_plan_perfil=cliente.plan.nombre_perfil
            )
            
        return Response({
            "message": f"Estado del cliente actualizado a {nuevo_estado}",
            "mikrotik_status": resultado,
            "cliente_estado": cliente.estado
        }, status=status.HTTP_200_OK)

from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import ClientePPPoE
from .serializers import ClientePPPoESerializer
from .services import MikroTikService
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter



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

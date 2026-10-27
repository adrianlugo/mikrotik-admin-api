from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import ClientePPPoE
from .serializers import ClientePPPoESerializer
from .services import MikroTikService
from rest_framework.decorators import action


class ClientePPPoEViewSet(viewsets.ModelViewSet):
    queryset = ClientePPPoE.objects.all()
    serializer_name = ClientePPPoESerializer
    serializer_class = ClientePPPoESerializer

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

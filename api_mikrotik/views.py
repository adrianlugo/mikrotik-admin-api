from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import ClientePPPoE
from .serializers import ClientePPPoESerializer
from .services import MikroTikService

class ClientePPPoEViewSet(viewsets.ModelViewSet):
    queryset = ClientePPPoE.objects.all()
    serializer_name = ClientePPPoESerializer
    serializer_class = ClientePPPoESerializer

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

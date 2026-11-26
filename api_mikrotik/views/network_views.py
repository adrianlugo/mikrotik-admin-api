from django.db import transaction
from rest_framework import viewsets, status, serializers
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from drf_spectacular.utils import extend_schema, extend_schema_view

from api_mikrotik.models import ClienteRed, PlanVelocidad
from api_mikrotik.serializers import ClienteRedSerializer, PlanVelocidadSerializer
from api_mikrotik.services import PPPoEService, NetworkClientService, TrafficService
from api_mikrotik.permissions import PermisoOperativo


@extend_schema_view(
    list=extend_schema(summary="Listar planes de velocidad", tags=['Planes de velocidad']),
    retrieve=extend_schema(summary="Consultar un plan de velocidad", tags=['Planes de velocidad']),
    create=extend_schema(summary="Crear un plan de velocidad", tags=['Planes de velocidad']),
    update=extend_schema(summary="Actualizar completamente un plan", tags=['Planes de velocidad']),
    partial_update=extend_schema(summary="Actualizar parcialmente un plan", tags=['Planes de velocidad']),
    destroy=extend_schema(summary="Eliminar un plan de velocidad", tags=['Planes de velocidad']),
)
class PlanVelocidadViewSet(viewsets.ModelViewSet):
    queryset = PlanVelocidad.objects.all()
    serializer_class = PlanVelocidadSerializer
    permission_classes = [PermisoOperativo]
    permite_tecnico_edicion = False

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            plan = serializer.save()
            pppoe_service = PPPoEService(plan.router)
            traffic_service = TrafficService(plan.router)

            if not plan.cola_padre:
                plan.cola_padre = f"Plan-{plan.nombre_perfil}"
                plan.save(update_fields=['cola_padre'])

            resultado = pppoe_service.crear_perfil_velocidad(
                nombre_perfil=plan.nombre_perfil,
                subida=f"{plan.subida_mbps}M",
                bajada=f"{plan.bajada_mbps}M",
                cola_padre=plan.cola_padre,
                direccion_local=plan.direccion_local,
                pool_remoto=plan.pool_remoto,
            )
            resultado_cola = traffic_service.asegurar_cola_padre(
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

            pppoe_service = PPPoEService(plan.router)
            traffic_service = TrafficService(plan.router)

            perfil = pppoe_service.crear_perfil_velocidad(
                nombre_perfil=plan.nombre_perfil,
                subida=f"{plan.subida_mbps}M",
                bajada=f"{plan.bajada_mbps}M",
                cola_padre=plan.cola_padre,
                direccion_local=plan.direccion_local,
                pool_remoto=plan.pool_remoto,
            )
            cola = traffic_service.asegurar_cola_padre(plan.cola_padre, plan.subida_mbps, plan.bajada_mbps)

            if perfil.get('status') == 'error':
                raise serializers.ValidationError({"mikrotik_error": perfil.get('message')})
            if cola.get('status') == 'error':
                raise serializers.ValidationError({"mikrotik_error": cola.get('message')})

        return Response({"plan": PlanVelocidadSerializer(plan).data, "mikrotik_status": perfil, "cola_padre_status": cola})


@extend_schema_view(
    list=extend_schema(summary="Listar clientes DHCP e IP fija", tags=['Clientes DHCP e IP fija']),
    retrieve=extend_schema(summary="Consultar un cliente DHCP o IP fija", tags=['Clientes DHCP e IP fija']),
    create=extend_schema(summary="Crear un cliente DHCP o IP fija", tags=['Clientes DHCP e IP fija']),
    update=extend_schema(summary="Actualizar completamente un cliente de red", tags=['Clientes DHCP e IP fija']),
    partial_update=extend_schema(summary="Actualizar parcialmente un cliente de red", tags=['Clientes DHCP e IP fija']),
    destroy=extend_schema(summary="Eliminar un cliente DHCP e IP fija", tags=['Clientes DHCP e IP fija']),
)
class ClienteRedViewSet(viewsets.ModelViewSet):
    queryset = ClienteRed.objects.select_related('router', 'plan').all()
    serializer_class = ClienteRedSerializer
    permission_classes = [PermisoOperativo]
    permite_tecnico_edicion = True
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['estado', 'router', 'plan', 'tipo']
    search_fields = ['nombre', 'direccion_ip', 'direccion_mac']

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cliente = serializer.save()

        servicio = NetworkClientService(cliente.router)
        reserva = servicio.sincronizar_reserva_cliente_red(cliente)
        if reserva.get('status') == 'error':
            cliente.delete()
            return Response({"mikrotik_error": reserva.get('message')}, status=status.HTTP_502_BAD_GATEWAY)

        cola = servicio.sincronizar_cola_cliente_red(cliente)
        if cola.get('status') == 'error':
            servicio.eliminar_reserva_cliente_red(cliente)
            cliente.delete()
            return Response({"mikrotik_error": cola.get('message')}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({
            "cliente": ClienteRedSerializer(cliente).data,
            "reserva_status": reserva,
            "cola_status": cola,
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        cliente = self.get_object()
        serializer = self.get_serializer(cliente, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        cliente = serializer.save()

        servicio = NetworkClientService(cliente.router)
        reserva = servicio.sincronizar_reserva_cliente_red(cliente)
        if reserva.get('status') == 'error':
            return Response({"mikrotik_error": reserva.get('message')}, status=status.HTTP_502_BAD_GATEWAY)

        cola = servicio.sincronizar_cola_cliente_red(cliente)
        if cola.get('status') == 'error':
            return Response({"mikrotik_error": cola.get('message')}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({
            "cliente": ClienteRedSerializer(cliente).data,
            "reserva_status": reserva,
            "cola_status": cola,
        })

    def destroy(self, request, *args, **kwargs):
        cliente = self.get_object()
        servicio = NetworkClientService(cliente.router)

        cola = servicio.eliminar_cola_cliente_red(cliente)
        if cola.get('status') == 'error':
            return Response({"mikrotik_error": cola.get('message')}, status=status.HTTP_502_BAD_GATEWAY)

        reserva = servicio.eliminar_reserva_cliente_red(cliente)
        if reserva.get('status') == 'error':
            return Response({"mikrotik_error": reserva.get('message')}, status=status.HTTP_502_BAD_GATEWAY)

        cliente.delete()
        return Response({"message": "Cliente, reserva y cola eliminados", "cola_status": cola, "reserva_status": reserva})

    @extend_schema(summary="Crear o reparar la cola del cliente", tags=['Clientes DHCP e IP fija'])
    @action(detail=True, methods=['post'], url_path='crear-cola')
    def crear_cola(self, request, pk=None):
        cliente = self.get_object()
        servicio = NetworkClientService(cliente.router)
        reserva = servicio.sincronizar_reserva_cliente_red(cliente)
        if reserva.get('status') == 'error':
            return Response(reserva, status=status.HTTP_502_BAD_GATEWAY)
        cola = servicio.sincronizar_cola_cliente_red(cliente)
        code = status.HTTP_200_OK if cola.get('status') == 'success' else status.HTTP_502_BAD_GATEWAY
        return Response({'reserva_status': reserva, 'cola_status': cola}, status=code)

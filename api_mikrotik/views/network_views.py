from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from drf_spectacular.utils import extend_schema, extend_schema_view

from api_mikrotik.exceptions import MikroTikConnectionError
from api_mikrotik.models import ClienteRed, PlanVelocidad
from api_mikrotik.serializers import ClienteRedSerializer, PlanVelocidadSerializer
from api_mikrotik.services import PPPoEService, NetworkClientService, TrafficService
from api_mikrotik.permissions import PermisoOperativo


def _quiere_crear_cola_padre(request):
    """True si la petición pide explícitamente crear la cola Plan-{perfil}.

    Acepta ``crear_cola_padre=true`` en el cuerpo JSON o en el formulario.
    Sin este flag, un plan sin cola padre se guarda sin cola padre (none)
    y la API no genera ninguna cola.
    """
    valor = request.data.get('crear_cola_padre', False)
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in ('1', 'true', 'yes', 'on', 'si', 'sí')


def _sincronizar_plan_en_router(plan, crear_cola_padre_explicito, es_actualizacion):
    """Crea/actualiza el perfil PPPoE y, si toca, la cola padre en el router.

    Orden seguro: primero el perfil y solo después la cola padre, para no
    tocar la cola si crear el perfil falla. Si el perfil falla, se lanza
    MikroTikConnectionError y la transacción que llamó revierte el plan
    en Django: un fallo del router es 502, nunca un error de validación
    (400).

    Cola padre:
    - Con nombre: se sincroniza el perfil con esa cola y se asegura la cola
      (si ya existe en el router, NO se toca su max-limit; si no existe, se
      crea con el límite del plan y se avisa de que eso capa el total).
    - Vacía y sin flag explícito: sin cola padre (none). En creación el
      perfil nuevo ya nace con parent-queue none; en actualización se envía
      parent-queue=none para quitar la cola anterior del perfil.
    - Vacía con ``crear_cola_padre=true``: se genera ``Plan-{nombre_perfil}``
      y se crea con el límite del plan (con el aviso de que capa el total).
    """
    if not plan.cola_padre and crear_cola_padre_explicito:
        plan.cola_padre = f"Plan-{plan.nombre_perfil}"
        plan.save(update_fields=['cola_padre'])

    pppoe_service = PPPoEService(plan.router)
    traffic_service = TrafficService(plan.router)

    cola_para_perfil = plan.cola_padre
    if not cola_para_perfil and es_actualizacion:
        cola_para_perfil = 'none'
    resultado = pppoe_service.crear_perfil_velocidad(
        nombre_perfil=plan.nombre_perfil,
        subida=f"{plan.subida_mbps}M",
        bajada=f"{plan.bajada_mbps}M",
        cola_padre=cola_para_perfil,
        direccion_local=plan.direccion_local,
        pool_remoto=plan.pool_remoto,
    )
    if resultado.get("status") == "error":
        raise MikroTikConnectionError(
            resultado.get("message") or "No se pudo sincronizar el perfil en el router."
        )

    if plan.cola_padre:
        resultado_cola = traffic_service.asegurar_cola_padre(
            plan.cola_padre, plan.subida_mbps, plan.bajada_mbps
        )
        if resultado_cola.get("status") == "error":
            raise MikroTikConnectionError(
                resultado_cola.get("message") or "No se pudo asegurar la cola padre en el router."
            )
    else:
        resultado_cola = {
            "status": "none",
            "message": (
                "Sin cola padre (none): el plan no tiene cola padre y la API "
                "no generó ninguna. Para crear la cola Plan-"
                f"{plan.nombre_perfil} con el "
                "límite del plan, repite la petición con crear_cola_padre=true "
                "(ojo: ese límite capa el total del plan; ver docs/api.md)."
            ),
        }
    return resultado, resultado_cola


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
            resultado, resultado_cola = _sincronizar_plan_en_router(
                plan, _quiere_crear_cola_padre(request), es_actualizacion=False
            )

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
            perfil, cola = _sincronizar_plan_en_router(
                plan, _quiere_crear_cola_padre(request), es_actualizacion=True
            )

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
        # Atómico: si la reserva o la cola fallan en el router, el
        # cliente NO queda guardado en Django. El fallo del router se
        # lanza como MikroTikConnectionError (502 con el formato único)
        # y la transacción revierte; si el servicio lanza cualquier otra
        # excepción, el manejador global la convierte en error y la
        # transacción también revierte. Antes se borraba el cliente a
        # mano tras el fallo, lo que dejaba hueco a borrados parciales.
        with transaction.atomic():
            cliente = serializer.save()

            servicio = NetworkClientService(cliente.router)
            reserva = servicio.sincronizar_reserva_cliente_red(cliente)
            if reserva.get('status') == 'error':
                raise MikroTikConnectionError(
                    reserva.get('message') or "No se pudo crear la reserva en el router."
                )

            cola = servicio.sincronizar_cola_cliente_red(cliente)
            if cola.get('status') == 'error':
                raise MikroTikConnectionError(
                    cola.get('message') or "No se pudo crear la cola en el router."
                )

        return Response({
            "cliente": ClienteRedSerializer(cliente).data,
            "reserva_status": reserva,
            "cola_status": cola,
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        cliente = self.get_object()
        serializer = self.get_serializer(cliente, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        # Atómico: si la reserva o la cola fallan en el router, los cambios
        # locales se revierten y la API devuelve 502. Antes el cliente
        # quedaba guardado en Django aunque el router hubiera fallado.
        with transaction.atomic():
            cliente = serializer.save()

            servicio = NetworkClientService(cliente.router)
            reserva = servicio.sincronizar_reserva_cliente_red(cliente)
            if reserva.get('status') == 'error':
                raise MikroTikConnectionError(
                    reserva.get('message') or "No se pudo actualizar la reserva en el router."
                )

            cola = servicio.sincronizar_cola_cliente_red(cliente)
            if cola.get('status') == 'error':
                raise MikroTikConnectionError(
                    cola.get('message') or "No se pudo actualizar la cola en el router."
                )

        return Response({
            "cliente": ClienteRedSerializer(cliente).data,
            "reserva_status": reserva,
            "cola_status": cola,
        })

    def destroy(self, request, *args, **kwargs):
        """Borra el cliente de red del router y de Django.

        Orden elegido, de fuera hacia dentro: primero la cola simple y
        luego la reserva DHCP/ARP, y el registro local solo al final.
        Si borrar la cola falla, no se ha tocado nada y se puede
        reintentar el borrado entero. Si borrar la reserva falla
        después de borrar la cola, el cliente sigue en Django (con la
        reserva aún en el router) y el borrado se puede reintentar:
        eliminar la cola de un cliente que ya no la tiene es
        idempotente (devuelve success si no la encuentra), así que el
        segundo intento no se atasca en la cola. No hay forma de hacer
        el borrado en el router y en Django en una sola transacción,
        así que este orden es el que deja el menor resto posible.
        """
        cliente = self.get_object()
        servicio = NetworkClientService(cliente.router)

        cola = servicio.eliminar_cola_cliente_red(cliente)
        if cola.get('status') == 'error':
            raise MikroTikConnectionError(
                cola.get('message') or "No se pudo eliminar la cola del router."
            )

        reserva = servicio.eliminar_reserva_cliente_red(cliente)
        if reserva.get('status') == 'error':
            raise MikroTikConnectionError(
                reserva.get('message') or "No se pudo eliminar la reserva del router."
            )

        cliente.delete()
        return Response({"message": "Cliente, reserva y cola eliminados", "cola_status": cola, "reserva_status": reserva})

    @extend_schema(summary="Crear o reparar la cola del cliente", tags=['Clientes DHCP e IP fija'])
    @action(detail=True, methods=['post'], url_path='crear-cola')
    def crear_cola(self, request, pk=None):
        cliente = self.get_object()
        servicio = NetworkClientService(cliente.router)
        reserva = servicio.sincronizar_reserva_cliente_red(cliente)
        if reserva.get('status') == 'error':
            raise MikroTikConnectionError(
                reserva.get('message') or "No se pudo sincronizar la reserva en el router."
            )
        cola = servicio.sincronizar_cola_cliente_red(cliente)
        if cola.get('status') == 'error':
            raise MikroTikConnectionError(
                cola.get('message') or "No se pudo sincronizar la cola en el router."
            )
        return Response({'reserva_status': reserva, 'cola_status': cola}, status=status.HTTP_200_OK)

import re
from rest_framework import serializers
from .models import ClientePPPoE, ClienteRed, Factura, Pago, PlanVelocidad, Router


class RouterSerializer(serializers.ModelSerializer):
    # write_only: la contraseña nunca se devuelve en las respuestas de la API.
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = Router
        fields = ('id', 'nombre', 'ip_address', 'puerto_api', 'usuario', 'password', 'activo', 'creado_en')

    def validate_puerto_api(self, value):
        # La API RouterOS solo usa 8729 (API-SSL, recomendado) y 8728
        # (sin cifrar, solo laboratorio). Cualquier otro puerto es un
        # error de configuración, no un router distinto.
        if value not in (8728, 8729):
            raise serializers.ValidationError(
                "El puerto de la API debe ser 8729 (API-SSL, recomendado) o 8728 (sin cifrar, solo laboratorio)."
            )
        return value

class ClientePPPoESerializer(serializers.ModelSerializer):
    # Declaramos explícitamente los campos para poder aplicar estilos de lectura en las respuestas
    router_nombre = serializers.CharField(source='router.nombre', read_only=True)
    plan_nombre = serializers.CharField(source='plan.nombre_perfil', read_only=True)
    # write_only: la contraseña nunca se devuelve en las respuestas de la API.
    password_pppoe = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = ClientePPPoE
        # portal_token queda fuera a propósito: es un secreto de portador y
        # solo se usa internamente para localizar al cliente en el portal.
        fields = ('id', 'router', 'router_nombre', 'plan', 'plan_nombre', 'usuario_pppoe', 'password_pppoe', 'nombre_completo', 'estado', 'direccion_ip_antena', 'creado_en')

    def validate_usuario_pppoe(self, value):
        """
        Valida que el usuario PPPoE sea seguro y compatible con MikroTik.
        No debe contener espacios, mayúsculas, eñes ni caracteres especiales complejos.
        """
        # Limpiamos espacios al inicio y al final
        value = value.strip().lower()
        # Validamos formato: solo letras minúsculas, números, puntos, guiones o guiones bajos
        if not re.match(r'^[a-z0-9._-]+$', value):
            raise serializers.ValidationError(
                "El usuario PPPoE solo puede contener letras minúsculas, números, puntos (.), guiones (-) y guiones bajos (_)."
            )
        return value

    def validate_password_pppoe(self, value):
        """
        Asegura que la contraseña del PPPoE cumpla con una longitud mínima
        para evitar problemas de seguridad en la red del cliente.
        """
        MIN_PASSWORD_LENGTH = 6
        if len(value) < MIN_PASSWORD_LENGTH:
            raise serializers.ValidationError(f"La contraseña del PPPoE debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.")
        return value

    def validate(self, data):
        """
        Validaciones cruzadas. Evita guardar un cliente activo en un
        router marcado como fuera de servicio, y evita asociar un plan
        de un router a un cliente de otro router (antes solo lo validaba
        ClienteRedSerializer; en PPPoE se podía crear el cliente con el
        plan de otro router y el secreto quedaba en el perfil equivocado).
        En actualizaciones parciales se usan los valores ya guardados
        para los campos que no vienen en la petición.
        """
        router = data.get('router') or getattr(self.instance, 'router', None)
        plan = data.get('plan') or getattr(self.instance, 'plan', None)
        estado = data.get('estado') or getattr(self.instance, 'estado', None)
        if router and plan and plan.router_id != router.id:
            raise serializers.ValidationError({
                "plan": "El plan seleccionado pertenece a otro router."
            })
        if router and hasattr(router, 'activo') and not router.activo and estado == 'activo':
            raise serializers.ValidationError({
                "router": "No se puede activar un cliente en un router que está marcado como fuera de servicio."
            })
        return data

class PlanVelocidadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanVelocidad
        fields = '__all__'
        # cola_padre es el nombre de una cola simple que ya existe en el
        # router (se elige en el desplegable de GET /api/routers/{id}/colas/).
        # Vacía significa «sin cola padre» (none): la API ya NO genera una
        # cola Plan-{nombre_perfil}. Si se quiere crear esa cola, se pide
        # explícitamente con crear_cola_padre=true al crear o editar el plan
        # (ver PlanVelocidadViewSet); su límite será el del plan y eso capa
        # el total del plan (ver docs/api.md, «Cola padre»).
        extra_kwargs = {
            'cola_padre': {
                'help_text': (
                    'Nombre de una cola simple que ya existe en el router. '
                    'Vacía = sin cola padre (none); la API no genera ninguna.'
                ),
            },
        }

    def validate_subida_mbps(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("La velocidad de subida debe ser mayor que 0 Mbps.")
        return value

    def validate_bajada_mbps(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("La velocidad de bajada debe ser mayor que 0 Mbps.")
        return value

    def validate_nombre_perfil(self, value):
        nombre = (value or '').strip()
        if not nombre:
            raise serializers.ValidationError("El nombre del perfil no puede estar vacío.")
        if not re.match(r'^[A-Za-z0-9._\- ]+$', nombre):
            raise serializers.ValidationError(
                "El nombre del perfil solo puede contener letras, números, espacios, puntos (.), guiones (-) y guiones bajos (_)."
            )
        # Los perfiles de sistema de RouterOS no son planes del ISP y la
        # sincronización no los importa como planes (ver PERFILES_SISTEMA
        # en services/pppoe.py): tampoco se pueden crear como plan aquí.
        if nombre in ('default', 'default-encryption'):
            raise serializers.ValidationError(
                f"'{nombre}' es un perfil de sistema de RouterOS, no un plan del ISP."
            )
        return nombre

    def validate_cola_padre(self, value):
        nombre = (value or '').strip()
        if nombre and not re.match(r'^[A-Za-z0-9._\- ]+$', nombre):
            raise serializers.ValidationError(
                "El nombre de la cola padre solo puede contener letras, números, espacios, puntos (.), guiones (-) y guiones bajos (_)."
            )
        return nombre

    def validate_pool_remoto(self, value):
        nombre = (value or '').strip()
        if nombre and not re.match(r'^[A-Za-z0-9._\-]+$', nombre):
            raise serializers.ValidationError(
                "El nombre del pool solo puede contener letras, números, puntos (.), guiones (-) y guiones bajos (_)."
            )
        return nombre

    # Nota: la existencia de cola_padre/pool_remoto en el router NO se
    # valida aquí: haría falta una llamada en vivo al router en cada
    # creación/edición de plan (y en modo simulación no hay router que
    # consultar). Si el nombre no existe, la sincronización del plan
    # falla con un 502 claro y el plan no se guarda (ver
    # _sincronizar_plan_en_router). La web ya ofrece los desplegables
    # de colas y pools del router para no escribir el nombre a mano.


class FacturaSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.nombre_completo', read_only=True)

    class Meta:
        model = Factura
        fields = '__all__'

    def validate_monto(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("El monto de la factura debe ser mayor que 0.")
        return value

    def validate(self, data):
        periodo = data.get('periodo') or getattr(self.instance, 'periodo', None)
        vencimiento = data.get('fecha_vencimiento') or getattr(self.instance, 'fecha_vencimiento', None)
        if periodo and vencimiento and vencimiento < periodo:
            raise serializers.ValidationError({
                "fecha_vencimiento": "La fecha de vencimiento no puede ser anterior al periodo facturado."
            })
        return data


class PagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pago
        fields = '__all__'
        read_only_fields = ('registrado_por',)

    def validate_monto(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("El monto del pago debe ser mayor que 0.")
        return value


class ClienteRedSerializer(serializers.ModelSerializer):
    router_nombre = serializers.CharField(source='router.nombre', read_only=True)
    plan_nombre = serializers.CharField(source='plan.nombre_perfil', read_only=True)

    class Meta:
        model = ClienteRed
        fields = '__all__'

    def validate(self, data):
        router = data.get('router') or getattr(self.instance, 'router', None)
        plan = data.get('plan') or getattr(self.instance, 'plan', None)
        tipo = data.get('tipo') or getattr(self.instance, 'tipo', None)
        if router and plan and plan.router_id != router.id:
            raise serializers.ValidationError({"plan": "El plan seleccionado pertenece a otro router."})
        direccion_mac = (data.get('direccion_mac', getattr(self.instance, 'direccion_mac', None)) or '').strip()
        if tipo == 'dhcp' and not direccion_mac:
            raise serializers.ValidationError({"direccion_mac": "Los clientes DHCP necesitan una MAC para crear el lease estático."})
        if not direccion_mac:
            raise serializers.ValidationError({"direccion_mac": "Las IP fijas necesitan una MAC para crear la reserva ARP."})
        if direccion_mac:
            mac = direccion_mac
            partes = mac.lower().split(':')
            if len(partes) != 6 or any(len(p) != 2 or not all(c in '0123456789abcdef' for c in p) for p in partes):
                raise serializers.ValidationError({"direccion_mac": "Formato MAC inválido. Use XX:XX:XX:XX:XX:XX."})
        return data

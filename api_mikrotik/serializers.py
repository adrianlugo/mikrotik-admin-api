import re
from rest_framework import serializers
from .models import ClientePPPoE, ClienteRed, Factura, Pago, PlanVelocidad, Router


class RouterSerializer(serializers.ModelSerializer):
    # write_only: la contraseña nunca se devuelve en las respuestas de la API.
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = Router
        fields = ('id', 'nombre', 'ip_address', 'puerto_api', 'usuario', 'password', 'activo', 'creado_en')

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
        Validaciones cruzadas (opcional). 
        Por ejemplo, evitar que se guarde un cliente activo si el enrutador asignado está inactivo.
        """
        router = data.get('router')
        estado = data.get('estado')
        # Ejemplo: Si tu modelo Router tiene un campo 'activo'
        if router and hasattr(router, 'activo') and not router.activo and estado == 'activo':
            raise serializers.ValidationError({
                "router": "No se puede activar un cliente en un router que está marcado como fuera de servicio."
            })
        return data

class PlanVelocidadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanVelocidad
        fields = '__all__'


class FacturaSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.nombre_completo', read_only=True)

    class Meta:
        model = Factura
        fields = '__all__'


class PagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pago
        fields = '__all__'
        read_only_fields = ('registrado_por',)


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
        direccion_mac = data.get('direccion_mac', getattr(self.instance, 'direccion_mac', '')).strip()
        if tipo == 'dhcp' and not direccion_mac:
            raise serializers.ValidationError({"direccion_mac": "Los clientes DHCP necesitan una MAC para crear el lease estático."})
        if not direccion_mac:
            raise serializers.ValidationError({"direccion_mac": "Las IP fijas necesitan una MAC para crear la reserva ARP."})
        if direccion_mac:
            mac = data.get('direccion_mac', self.instance.direccion_mac if self.instance else '')
            partes = mac.lower().split(':')
            if len(partes) != 6 or any(len(p) != 2 or not all(c in '0123456789abcdef' for c in p) for p in partes):
                raise serializers.ValidationError({"direccion_mac": "Formato MAC inválido. Use XX:XX:XX:XX:XX:XX."})
        return data

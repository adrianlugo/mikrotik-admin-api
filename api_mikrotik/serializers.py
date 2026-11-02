import re
from rest_framework import serializers
from .models import ClientePPPoE, PlanVelocidad, Router


class RouterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = Router
        fields = '__all__'

class ClientePPPoESerializer(serializers.ModelSerializer):
    # Declaramos explícitamente los campos para poder aplicar estilos de lectura en las respuestas
    router_nombre = serializers.CharField(source='router.nombre', read_only=True)
    plan_nombre = serializers.CharField(source='plan.nombre', read_only=True)

    class Meta:
        model = ClientePPPoE
        fields = '__all__'

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
        fields = '__all__'  # Esto expondrá id, nombre, nombre_perfil, etc.

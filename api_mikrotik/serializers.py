from rest_framework import serializers
from .models import ClientePPPoE

class ClientePPPoESerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientePPPoE
        fields = '__all__'

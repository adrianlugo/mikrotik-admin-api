"""Tests de humo para los arreglos críticos de 2026-11-25.

Cazan directamente los dos fallos funcionales de la revisión:
- POST /api/planes/ fallaba con NameError (faltaba importar transaction).
- `python manage.py cortar_facturas_vencidas` fallaba con ImportError
  (importaba MikroTikService, que no existe).

Y cubren los arreglos de seguridad: las contraseñas ya no se exponen en
las respuestas de la API, el cifrado en reposo funciona y la conexión
RouterOS usa API-SSL por defecto.
"""

import os
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from api_mikrotik.crypto import decrypt_value, encrypt_value
from api_mikrotik.exceptions import MikroTikConnectionError
from api_mikrotik.models import ClientePPPoE, PlanVelocidad, Router
from api_mikrotik.serializers import ClientePPPoESerializer, RouterSerializer
from api_mikrotik.services import MikroTikBaseService


class CriticalFixesSmokeTests(TestCase):
    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas', ip_address='192.0.2.1', usuario='api', password='clave-router'
        )
        self.plan = PlanVelocidad.objects.create(
            router=self.router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        self.user = get_user_model().objects.create_superuser(
            username='admin', email='a@a.com', password='admin1234'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_cortar_facturas_vencidas_imports_and_runs(self):
        # Antes del arreglo esto fallaba al importar: MikroTikService no existe.
        from django.core.management.base import BaseCommand

        from api_mikrotik.management.commands.cortar_facturas_vencidas import Command

        self.assertTrue(issubclass(Command, BaseCommand))
        # Sin facturas vencidas no toca ningún router y termina en éxito.
        call_command('cortar_facturas_vencidas')

    def test_post_planes_creates_plan(self):
        # Antes del arreglo esto fallaba con NameError: transaction no estaba
        # importado en api_mikrotik/views/network_views.py.
        class FakePPPoE:
            def __init__(self, router):
                pass

            def crear_perfil_velocidad(self, **kwargs):
                return {'status': 'success'}

        class FakeTraffic:
            def __init__(self, router):
                pass

            def asegurar_cola_padre(self, *args):
                return {'status': 'success'}

        with patch('api_mikrotik.views.network_views.PPPoEService', FakePPPoE), \
                patch('api_mikrotik.views.network_views.TrafficService', FakeTraffic):
            response = self.client.post('/api/planes/', {
                'router': self.router.id,
                'nombre_perfil': '20M',
                'subida_mbps': 20,
                'bajada_mbps': 20,
            }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(PlanVelocidad.objects.filter(nombre_perfil='20M').exists())

    def test_serializers_do_not_expose_passwords_or_portal_token(self):
        cliente = ClientePPPoE.objects.create(
            router=self.router, plan=self.plan, usuario_pppoe='cliente.prueba',
            password_pppoe='clave123', nombre_completo='Cliente de prueba'
        )
        self.assertNotIn('password', RouterSerializer(self.router).data)
        cliente_data = ClientePPPoESerializer(cliente).data
        self.assertNotIn('password_pppoe', cliente_data)
        self.assertNotIn('portal_token', cliente_data)

    def test_password_can_be_written_and_is_read_back_decrypted(self):
        cliente = ClientePPPoE.objects.create(
            router=self.router, plan=self.plan, usuario_pppoe='cliente.otro',
            password_pppoe='clave123', nombre_completo='Otro cliente'
        )
        self.assertEqual(cliente.get_password_pppoe(), 'clave123')
        self.assertEqual(self.router.get_password(), 'clave-router')

    def test_crypto_roundtrip_when_key_is_configured(self):
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {'MIKROTIK_CREDENTIALS_KEY': key}):
            cifrado = encrypt_value('secreto')
            self.assertTrue(cifrado.startswith('ENC1:'))
            self.assertEqual(decrypt_value(cifrado), 'secreto')

    def test_crypto_legacy_plaintext_passes_through(self):
        self.assertEqual(decrypt_value('clave123'), 'clave123')
        self.assertEqual(encrypt_value('clave123'), 'clave123')

    def test_router_connection_uses_ssl_on_port_8729(self):
        self.router.puerto_api = 8729
        self.router.save(update_fields=['puerto_api'])

        class FakePool:
            def __init__(self, *args, **kwargs):
                FakePool.kwargs = kwargs

            def get_api(self):
                return object()

        with patch('routeros_api.RouterOsApiPool', FakePool):
            MikroTikBaseService(self.router)._obtener_conexion_real()

        self.assertEqual(FakePool.kwargs['port'], 8729)
        self.assertTrue(FakePool.kwargs['use_ssl'])
        # plaintext_login=True es obligatorio en RouterOS >= 6.43, pero la
        # contraseña viaja dentro de la sesión TLS, no en texto plano.
        self.assertTrue(FakePool.kwargs['plaintext_login'])

    @override_settings(MIKROTIK_ALLOW_INSECURE_API=False)
    def test_router_connection_refuses_plaintext_without_ssl(self):
        self.router.puerto_api = 8728
        self.router.save(update_fields=['puerto_api'])

        with self.assertRaises(MikroTikConnectionError):
            MikroTikBaseService(self.router)._obtener_conexion_real()

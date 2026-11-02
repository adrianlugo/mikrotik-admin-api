from unittest.mock import patch

from django.test import TestCase

from .models import ClientePPPoE, PlanVelocidad, Router
from .services import MikroTikService


class FakeResource:
    def __init__(self, rows):
        self.rows = rows
        self.added = []
        self.updated = []

    def get(self):
        return self.rows

    def add(self, **kwargs):
        self.added.append(kwargs)

    def set(self, **kwargs):
        self.updated.append(kwargs)


class FakeApi:
    def __init__(self):
        self.profiles = FakeResource([])
        self.secrets = FakeResource([])

    def get_resource(self, path):
        return self.profiles if path == '/ppp/profile' else self.secrets


class BidirectionalSyncTests(TestCase):
    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas', ip_address='192.0.2.1', usuario='api', password='secreta'
        )
        self.plan = PlanVelocidad.objects.create(
            router=self.router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        ClientePPPoE.objects.create(
            router=self.router, plan=self.plan, usuario_pppoe='cliente.prueba',
            password_pppoe='clave123', nombre_completo='Cliente de prueba'
        )
        self.fake_api = FakeApi()

    @patch.object(MikroTikService, '_obtener_conexion_real')
    def test_local_data_is_created_on_router(self, obtener_conexion_real):
        obtener_conexion_real.return_value = self.fake_api

        resultado = MikroTikService(self.router).sincronizar_bidireccional()

        self.assertEqual(resultado['status'], 'success')
        self.assertEqual(self.fake_api.profiles.added, [
            {'name': '10M', 'rate-limit': '10M/10M'}
        ])
        self.assertEqual(self.fake_api.secrets.added, [{
            'name': 'cliente.prueba', 'password': 'clave123',
            'profile': '10M', 'service': 'pppoe'
        }])

    def test_router_id_accepts_dot_id_and_plain_id(self):
        self.assertEqual(MikroTikService._obtener_id_router({'.id': '*1'}), '*1')
        self.assertEqual(MikroTikService._obtener_id_router({'id': '*2'}), '*2')

    @patch.object(MikroTikService, '_obtener_conexion_real')
    def test_existing_router_items_with_plain_id_can_be_updated(self, obtener_conexion_real):
        self.fake_api.profiles = FakeResource([{
            'id': '*1', 'name': '10M', 'rate-limit': '10M/10M'
        }])
        obtener_conexion_real.return_value = self.fake_api

        resultado = MikroTikService(self.router).sincronizar_bidireccional()

        self.assertEqual(resultado['status'], 'success')
        self.assertEqual(self.fake_api.profiles.updated, [{
            'id': '*1', 'rate-limit': '10M/10M'
        }])

    def test_rate_limit_conversion_supports_router_units(self):
        self.assertEqual(
            MikroTikService._velocidades_desde_router('5M/20M'),
            (5, 20)
        )
        self.assertEqual(
            MikroTikService._velocidades_desde_router('10240k/20480k'),
            (10, 20)
        )

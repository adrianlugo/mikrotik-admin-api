from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from api_mikrotik.utils import convertir_rate_limit_a_mbps

from api_mikrotik.models import ClientePPPoE, PlanVelocidad, Router
from api_mikrotik.services import PPPoEService
from api_mikrotik.views import ClientePPPoEViewSet


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
        self.resources = {}

    def get_resource(self, path):
        if path == '/ppp/profile':
            return self.profiles
        if path == '/ppp/secret':
            return self.secrets
        return self.resources.setdefault(path, FakeResource([]))


class PPPoESyncTests(TestCase):
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

    @patch.object(PPPoEService, '_obtener_conexion_real')
    def test_local_data_is_created_on_router(self, obtener_conexion_real):
        obtener_conexion_real.return_value = self.fake_api

        resultado = PPPoEService(self.router).sincronizar_bidireccional()

        self.assertEqual(resultado['status'], 'success')
        self.assertEqual(self.fake_api.profiles.added, [
            {'name': '10M', 'rate-limit': '10M/10M'}
        ])
        self.assertEqual(self.fake_api.secrets.added, [{
            'name': 'cliente.prueba', 'password': 'clave123',
            'profile': '10M', 'service': 'pppoe'
        }])

    @patch.object(PPPoEService, '_obtener_conexion_real')
    def test_existing_router_items_with_plain_id_can_be_updated(self, obtener_conexion_real):
        self.fake_api.profiles = FakeResource([{
            'id': '*1', 'name': '10M', 'rate-limit': '10M/10M'
        }])
        obtener_conexion_real.return_value = self.fake_api

        resultado = PPPoEService(self.router).sincronizar_bidireccional()

        self.assertEqual(resultado['status'], 'success')
        self.assertEqual(self.fake_api.profiles.updated, [{
            'id': '*1', 'rate-limit': '10M/10M'
        }])

    def test_rate_limit_conversion_supports_router_units(self):
        self.assertEqual(
            convertir_rate_limit_a_mbps('5M/20M'),
            (5, 20)
        )
        self.assertEqual(
            convertir_rate_limit_a_mbps('10240k/20480k'),
            (10, 20)
        )


class ActivePPPoEEndpointTests(TestCase):
    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas',
            ip_address='192.0.2.1',
            usuario='api',
            password='secreta',
        )
        self.plan = PlanVelocidad.objects.create(
            router=self.router,
            nombre_perfil='10M',
            subida_mbps=10,
            bajada_mbps=10,
        )
        ClientePPPoE.objects.create(
            router=self.router,
            plan=self.plan,
            usuario_pppoe='cliente.activo',
            password_pppoe='clave123',
            nombre_completo='Cliente activo',
        )
        self.user = get_user_model().objects.create_superuser(
            username='admin.pruebas',
            email='admin@example.com',
            password='clave123',
        )

    @patch.object(
        PPPoEService,
        'obtener_conexiones_activas',
        return_value=['cliente.activo'],
    )
    def test_listar_activos_finds_routers_with_pppoe_clients(self, obtener_conexiones):
        request = APIRequestFactory().get('/api/clientes-pppoe/activos/')
        force_authenticate(request, user=self.user)

        response = ClientePPPoEViewSet.as_view({'get': 'listar_activos'})(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_conectados'], 1)
        self.assertEqual(response.data['conexiones'], [
            'cliente.activo',
        ])
        obtener_conexiones.assert_called_once()
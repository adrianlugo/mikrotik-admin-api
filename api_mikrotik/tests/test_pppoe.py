from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from api_mikrotik.utils import convertir_rate_limit_a_mbps

from api_mikrotik.models import ClientePPPoE, PlanVelocidad, Router
from api_mikrotik.services import PPPoEService
from api_mikrotik.views import ClientePPPoEViewSet, RouterViewSet


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
        self.addresses = FakeResource([])
        self.pools = FakeResource([])
        self.resources = {}

    def get_resource(self, path):
        if path == '/ppp/profile':
            return self.profiles
        if path == '/ppp/secret':
            return self.secrets
        if path == '/ip/address':
            return self.addresses
        if path == '/ip/pool':
            return self.pools
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


class PerfilVelocidadLocalPoolTests(TestCase):
    """El perfil PPPoE lleva local-address (IP del loopback) y
    remote-address (nombre del pool), y ambos son opcionales."""

    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas', ip_address='192.0.2.1', usuario='api', password='clave-router'
        )
        self.fake_api = FakeApi()

    @patch.object(PPPoEService, '_obtener_conexion_real')
    def test_crear_perfil_con_direccion_local_y_pool(self, obtener_conexion_real):
        obtener_conexion_real.return_value = self.fake_api

        resultado = PPPoEService(self.router).crear_perfil_velocidad(
            '3mb', '3M', '3M',
            direccion_local='10.1.1.1', pool_remoto='pool-pppoe',
        )

        self.assertEqual(resultado['status'], 'success')
        self.assertEqual(self.fake_api.profiles.added, [{
            'name': '3mb', 'rate-limit': '3M/3M',
            'local-address': '10.1.1.1', 'remote-address': 'pool-pppoe',
        }])

    @patch.object(PPPoEService, '_obtener_conexion_real')
    def test_crear_perfil_sin_direccion_local_ni_pool_no_toca_esos_campos(self, obtener_conexion_real):
        # Compatibilidad: un plan sin direccion_local ni pool_remoto sigue
        # creando el perfil solo con rate-limit, como antes.
        obtener_conexion_real.return_value = self.fake_api

        resultado = PPPoEService(self.router).crear_perfil_velocidad('10M', '10M', '10M')

        self.assertEqual(resultado['status'], 'success')
        self.assertEqual(self.fake_api.profiles.added, [
            {'name': '10M', 'rate-limit': '10M/10M'}
        ])

    @patch.object(PPPoEService, '_obtener_conexion_real')
    def test_actualizar_perfil_existente_con_direccion_local_y_pool(self, obtener_conexion_real):
        self.fake_api.profiles = FakeResource([{
            'id': '*1', 'name': '3mb', 'rate-limit': '3M/3M',
        }])
        obtener_conexion_real.return_value = self.fake_api

        resultado = PPPoEService(self.router).crear_perfil_velocidad(
            '3mb', '3M', '3M',
            direccion_local='10.1.1.1', pool_remoto='pool-pppoe',
        )

        self.assertEqual(resultado['status'], 'success')
        self.assertEqual(self.fake_api.profiles.updated, [{
            'id': '*1', 'rate-limit': '3M/3M',
            'local-address': '10.1.1.1', 'remote-address': 'pool-pppoe',
        }])
        self.assertEqual(self.fake_api.profiles.added, [])

    @patch.object(PPPoEService, '_obtener_conexion_real')
    def test_sincronizar_importa_direccion_local_y_pool_del_router(self, obtener_conexion_real):
        self.fake_api.profiles = FakeResource([{
            'id': '*1', 'name': '3mb', 'rate-limit': '3M/3M',
            'local-address': '10.1.1.1', 'remote-address': 'pool-pppoe',
        }])
        obtener_conexion_real.return_value = self.fake_api

        resultado = PPPoEService(self.router).sincronizar_bidireccional()

        self.assertEqual(resultado['status'], 'success')
        plan = PlanVelocidad.objects.get(router=self.router, nombre_perfil='3mb')
        self.assertEqual(str(plan.direccion_local), '10.1.1.1')
        self.assertEqual(plan.pool_remoto, 'pool-pppoe')

    @patch.object(PPPoEService, '_obtener_conexion_real')
    def test_sincronizar_empuja_direccion_local_y_pool_a_mikrotik(self, obtener_conexion_real):
        PlanVelocidad.objects.create(
            router=self.router, nombre_perfil='3mb', subida_mbps=3, bajada_mbps=3,
            direccion_local='10.1.1.1', pool_remoto='pool-pppoe',
        )
        obtener_conexion_real.return_value = self.fake_api

        resultado = PPPoEService(self.router).sincronizar_bidireccional()

        self.assertEqual(resultado['status'], 'success')
        self.assertEqual(self.fake_api.profiles.added, [{
            'name': '3mb', 'rate-limit': '3M/3M',
            'local-address': '10.1.1.1', 'remote-address': 'pool-pppoe',
        }])


class DireccionesYPoolsTests(TestCase):
    """Listados de solo lectura para los desplegables de local-address y
    remote-address al crear o editar un plan."""

    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas', ip_address='192.0.2.1', usuario='api', password='clave-router'
        )
        self.fake_api = FakeApi()
        self.fake_api.addresses = FakeResource([
            {'interface': 'loopback', 'address': '10.1.1.1/32', 'network': '10.1.1.1', 'disabled': 'false'},
            {'interface': 'bridge-general', 'address': '192.168.88.1/24', 'network': '192.168.88.0', 'disabled': 'false'},
        ])
        self.fake_api.pools = FakeResource([
            {'name': 'pool-pppoe', 'ranges': '10.0.0.2-10.0.0.254'},
        ])
        self.user = get_user_model().objects.create_superuser(
            username='admin.pruebas',
            email='admin@example.com',
            password='clave-admin-123',
        )

    @patch.object(PPPoEService, '_obtener_conexion_real')
    def test_listar_direcciones_ip_devuelve_ip_sin_mascara(self, obtener_conexion_real):
        obtener_conexion_real.return_value = self.fake_api

        direcciones = PPPoEService(self.router).listar_direcciones_ip()

        # El desplegable muestra interfaz + IP, pero se guarda solo la IP.
        self.assertEqual(direcciones[0], {
            'interfaz': 'loopback',
            'direccion': '10.1.1.1',
            'direccion_con_mascara': '10.1.1.1/32',
            'red': '10.1.1.1',
            'deshabilitada': 'false',
        })
        self.assertEqual(direcciones[1]['direccion'], '192.168.88.1')

    @patch.object(PPPoEService, '_obtener_conexion_real')
    def test_listar_pools_devuelve_nombre_y_rangos(self, obtener_conexion_real):
        obtener_conexion_real.return_value = self.fake_api

        pools = PPPoEService(self.router).listar_pools()

        self.assertEqual(pools, [
            {'nombre': 'pool-pppoe', 'rangos': '10.0.0.2-10.0.0.254'},
        ])

    @patch.object(PPPoEService, 'listar_direcciones_ip')
    def test_endpoint_direcciones_ip(self, listar_direcciones):
        listar_direcciones.return_value = [
            {'interfaz': 'loopback', 'direccion': '10.1.1.1',
             'direccion_con_mascara': '10.1.1.1/32', 'red': '10.1.1.1',
             'deshabilitada': 'false'},
        ]
        request = APIRequestFactory().get(f'/api/routers/{self.router.id}/direcciones-ip/')
        force_authenticate(request, user=self.user)

        response = RouterViewSet.as_view({'get': 'direcciones_ip'})(request, pk=self.router.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 1)
        self.assertEqual(response.data['direcciones'][0]['direccion'], '10.1.1.1')

    @patch.object(PPPoEService, 'listar_pools')
    def test_endpoint_pools(self, listar_pools):
        listar_pools.return_value = [
            {'nombre': 'pool-pppoe', 'rangos': '10.0.0.2-10.0.0.254'},
        ]
        request = APIRequestFactory().get(f'/api/routers/{self.router.id}/pools/')
        force_authenticate(request, user=self.user)

        response = RouterViewSet.as_view({'get': 'pools'})(request, pk=self.router.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 1)
        self.assertEqual(response.data['pools'][0]['nombre'], 'pool-pppoe')


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

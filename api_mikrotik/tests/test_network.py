from unittest.mock import patch
from django.test import TestCase

from api_mikrotik.models import ClienteRed, PlanVelocidad, Router
from api_mikrotik.services import NetworkClientService


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
        self.resources = {}

    def get_resource(self, path):
        return self.resources.setdefault(path, FakeResource([]))


class NetworkClientSyncTests(TestCase):
    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas', ip_address='192.0.2.1', usuario='api', password='secreta'
        )
        self.plan = PlanVelocidad.objects.create(
            router=self.router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        self.fake_api = FakeApi()

    @patch.object(NetworkClientService, '_obtener_conexion_real')
    def test_dhcp_client_creates_static_lease(self, obtener_conexion_real):
        obtener_conexion_real.return_value = self.fake_api
        cliente = ClienteRed.objects.create(
            router=self.router, plan=self.plan, nombre='Casa DHCP', tipo='dhcp',
            direccion_ip='192.168.88.50', direccion_mac='AA:BB:CC:DD:EE:01',
        )

        resultado = NetworkClientService(self.router).sincronizar_reserva_cliente_red(cliente)

        self.assertEqual(resultado['status'], 'success')
        lease = self.fake_api.resources['/ip/dhcp-server/lease'].added[0]
        self.assertEqual(lease['address'], '192.168.88.50')
        self.assertEqual(lease['mac-address'], 'AA:BB:CC:DD:EE:01')

    @patch.object(NetworkClientService, '_obtener_conexion_real')
    def test_fixed_ip_client_creates_static_arp(self, obtener_conexion_real):
        obtener_conexion_real.return_value = self.fake_api
        cliente = ClienteRed.objects.create(
            router=self.router, plan=self.plan, nombre='Antena fija', tipo='ip_fija',
            direccion_ip='192.168.88.51', direccion_mac='AA:BB:CC:DD:EE:02',
            interfaz_mikrotik='bridge-general',
        )

        resultado = NetworkClientService(self.router).sincronizar_reserva_cliente_red(cliente)

        self.assertEqual(resultado['status'], 'success')
        arp = self.fake_api.resources['/ip/arp'].added[0]
        self.assertEqual(arp['interface'], 'bridge-general')
        self.assertEqual(arp['address'], '192.168.88.51')
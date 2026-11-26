"""Tests de la preparación para producción (2026-11-26).

Cubren: cola padre que no toca una cola existente, vacío = sin cola padre,
creación explícita de la cola, orden perfil-antes-que-cola, sincronización
sin contraseña débil ni planes inventados, corte sin Perfil_Corte,
plan-router en PPPoE, ClienteRed.update atómico, errores honestos del
router, revocación/rotación/expiración de tokens, paginación y respaldo.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api_mikrotik.exceptions import MikroTikConnectionError
from api_mikrotik.models import ClientePPPoE, ClienteRed, Factura, PlanVelocidad, Router
from api_mikrotik.serializers import ClientePPPoESerializer
from api_mikrotik.services import PPPoEService, TrafficService


class FakeResource:
    def __init__(self, rows):
        self.rows = rows
        self.added = []
        self.updated = []
        self.removed = []

    def get(self):
        return list(self.rows)

    def add(self, **kwargs):
        self.added.append(kwargs)
        self.rows.append(kwargs)

    def set(self, **kwargs):
        self.updated.append(kwargs)

    def remove(self, **kwargs):
        self.removed.append(kwargs)


class FakeApi:
    def __init__(self):
        self.profiles = FakeResource([])
        self.secrets = FakeResource([])
        self.queues = FakeResource([])
        self.active = FakeResource([])
        self.resources = {}

    def get_resource(self, path):
        if path == '/ppp/profile':
            return self.profiles
        if path == '/ppp/secret':
            return self.secrets
        if path == '/queue/simple':
            return self.queues
        if path == '/ppp/active':
            return self.active
        return self.resources.setdefault(path, FakeResource([]))

    def get_binary_resource(self, path):
        raise TypeError("el recurso binario no acepta estos argumentos")


def _usuario_admin():
    return get_user_model().objects.create_superuser(
        username='admin', email='a@a.com', password='clave-admin'
    )


class ColaPadreTests(TestCase):
    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas', ip_address='192.0.2.1', usuario='api', password='clave'
        )
        self.fake_api = FakeApi()

    @patch.object(TrafficService, '_obtener_conexion_real')
    def test_cola_existente_no_se_toca(self, obtener_conexion_real):
        self.fake_api.queues = FakeResource([
            {'id': '*1', 'name': 'Cola-Total', 'max-limit': '50M/50M'},
        ])
        obtener_conexion_real.return_value = self.fake_api

        resultado = TrafficService(self.router).asegurar_cola_padre('Cola-Total', 10, 10)

        self.assertEqual(resultado['status'], 'success')
        self.assertFalse(resultado['creada'])
        self.assertEqual(self.fake_api.queues.updated, [])
        self.assertEqual(self.fake_api.queues.added, [])

    @patch.object(TrafficService, '_obtener_conexion_real')
    def test_cola_inexistente_se_crea_con_limite_del_plan_y_aviso(self, obtener_conexion_real):
        obtener_conexion_real.return_value = self.fake_api

        resultado = TrafficService(self.router).asegurar_cola_padre('Plan-10M', 10, 10)

        self.assertEqual(resultado['status'], 'success')
        self.assertTrue(resultado['creada'])
        self.assertEqual(
            self.fake_api.queues.added,
            [{'name': 'Plan-10M', 'max-limit': '10M/10M',
              'comment': 'Cola padre administrada por ISP API'}],
        )
        self.assertIn('capa el total', resultado['message'])


class PlanSinColaPadreTests(TestCase):
    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas', ip_address='192.0.2.1', usuario='api', password='clave'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=_usuario_admin())

    def test_crear_plan_sin_cola_padre_queda_en_none(self):
        class FakePPPoE:
            def __init__(self, router):
                pass

            def crear_perfil_velocidad(self, **kwargs):
                return {'status': 'success'}

        class FakeTraffic:
            llamadas = []

            def __init__(self, router):
                pass

            def asegurar_cola_padre(self, *args):
                FakeTraffic.llamadas.append(args)
                return {'status': 'success'}

        with patch('api_mikrotik.views.network_views.PPPoEService', FakePPPoE), \
                patch('api_mikrotik.views.network_views.TrafficService', FakeTraffic):
            response = self.client.post('/api/planes/', {
                'router': self.router.id, 'nombre_perfil': '10M',
                'subida_mbps': 10, 'bajada_mbps': 10,
            }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan = PlanVelocidad.objects.get(nombre_perfil='10M')
        self.assertEqual(plan.cola_padre, '')
        self.assertEqual(FakeTraffic.llamadas, [])
        self.assertEqual(response.data['cola_padre_status']['status'], 'none')

    def test_crear_plan_con_flag_crea_la_cola_plan(self):
        class FakePPPoE:
            def __init__(self, router):
                pass

            def crear_perfil_velocidad(self, **kwargs):
                return {'status': 'success'}

        class FakeTraffic:
            llamadas = []

            def __init__(self, router):
                pass

            def asegurar_cola_padre(self, *args):
                FakeTraffic.llamadas.append(args)
                return {'status': 'success', 'creada': True}

        with patch('api_mikrotik.views.network_views.PPPoEService', FakePPPoE), \
                patch('api_mikrotik.views.network_views.TrafficService', FakeTraffic):
            response = self.client.post('/api/planes/', {
                'router': self.router.id, 'nombre_perfil': '10M',
                'subida_mbps': 10, 'bajada_mbps': 10,
                'crear_cola_padre': True,
            }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan = PlanVelocidad.objects.get(nombre_perfil='10M')
        self.assertEqual(plan.cola_padre, 'Plan-10M')
        self.assertEqual(FakeTraffic.llamadas, [('Plan-10M', 10, 10)])

    def test_actualizar_plan_sin_cola_padre_quita_parent_queue(self):
        plan = PlanVelocidad.objects.create(
            router=self.router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10,
            cola_padre='Cola-Vieja',
        )
        llamadas_perfil = []

        class FakePPPoE:
            def __init__(self, router):
                pass

            def crear_perfil_velocidad(self, **kwargs):
                llamadas_perfil.append(kwargs)
                return {'status': 'success'}

        class FakeTraffic:
            def __init__(self, router):
                pass

            def asegurar_cola_padre(self, *args):
                raise AssertionError('no se debe tocar la cola padre')

        with patch('api_mikrotik.views.network_views.PPPoEService', FakePPPoE), \
                patch('api_mikrotik.views.network_views.TrafficService', FakeTraffic):
            response = self.client.patch(f'/api/planes/{plan.id}/', {
                'cola_padre': '',
            }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(llamadas_perfil[0]['cola_padre'], 'none')
        plan.refresh_from_db()
        self.assertEqual(plan.cola_padre, '')

    def test_si_el_perfil_falla_no_se_toca_la_cola(self):
        class FakePPPoE:
            def __init__(self, router):
                pass

            def crear_perfil_velocidad(self, **kwargs):
                return {'status': 'error', 'message': 'el router rechazó el perfil'}

        class FakeTraffic:
            llamadas = []

            def __init__(self, router):
                pass

            def asegurar_cola_padre(self, *args):
                FakeTraffic.llamadas.append(args)
                return {'status': 'success'}

        with patch('api_mikrotik.views.network_views.PPPoEService', FakePPPoE), \
                patch('api_mikrotik.views.network_views.TrafficService', FakeTraffic):
            response = self.client.post('/api/planes/', {
                'router': self.router.id, 'nombre_perfil': '10M',
                'subida_mbps': 10, 'bajada_mbps': 10,
                'cola_padre': 'Cola-Total',
            }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(FakeTraffic.llamadas, [])
        self.assertFalse(PlanVelocidad.objects.filter(nombre_perfil='10M').exists())


class SincronizacionSeguraTests(TestCase):
    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas', ip_address='192.0.2.1', usuario='api', password='clave'
        )
        self.plan = PlanVelocidad.objects.create(
            router=self.router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        self.fake_api = FakeApi()

    @patch.object(PPPoEService, '_obtener_conexion_real')
    def test_secreto_sin_password_no_se_importa(self, obtener_conexion_real):
        self.fake_api.secrets = FakeResource([
            {'id': '*1', 'name': 'sin.clave', 'profile': '10M', 'password': ''},
            {'id': '*2', 'name': 'con.clave', 'profile': '10M', 'password': 'clave123'},
        ])
        obtener_conexion_real.return_value = self.fake_api

        resultado = PPPoEService(self.router).sincronizar_bidireccional()

        self.assertEqual(resultado['status'], 'success')
        self.assertFalse(ClientePPPoE.objects.filter(usuario_pppoe='sin.clave').exists())
        self.assertTrue(ClientePPPoE.objects.filter(usuario_pppoe='con.clave').exists())
        self.assertIn('sin.clave', resultado['details']['secretos_saltados_sin_password'])
        self.assertIn('sin.clave', resultado['details']['advertencias'][0])

    @patch.object(PPPoEService, '_obtener_conexion_real')
    def test_secreto_con_perfil_inexistente_no_inventa_plan(self, obtener_conexion_real):
        self.fake_api.secrets = FakeResource([
            {'id': '*1', 'name': 'cliente.raro', 'profile': 'PlanQueNoExiste',
             'password': 'clave123'},
        ])
        obtener_conexion_real.return_value = self.fake_api

        resultado = PPPoEService(self.router).sincronizar_bidireccional()

        self.assertEqual(resultado['status'], 'success')
        self.assertFalse(PlanVelocidad.objects.filter(nombre_perfil='PlanQueNoExiste').exists())
        self.assertFalse(ClientePPPoE.objects.filter(usuario_pppoe='cliente.raro').exists())
        self.assertTrue(any('cliente.raro' in item for item in resultado['details']['secretos_saltados_sin_plan']))

    @patch.object(PPPoEService, '_obtener_conexion_real')
    def test_perfil_de_sistema_no_se_importa_como_plan(self, obtener_conexion_real):
        self.fake_api.profiles = FakeResource([
            {'id': '*1', 'name': 'default', 'rate-limit': '5M/10M'},
            {'id': '*2', 'name': 'default-encryption', 'rate-limit': '5M/10M'},
        ])
        self.fake_api.secrets = FakeResource([
            {'id': '*3', 'name': 'cliente.default', 'profile': 'default',
             'password': 'clave123'},
        ])
        obtener_conexion_real.return_value = self.fake_api

        resultado = PPPoEService(self.router).sincronizar_bidireccional()

        self.assertEqual(resultado['status'], 'success')
        self.assertFalse(PlanVelocidad.objects.filter(nombre_perfil='default').exists())
        self.assertFalse(PlanVelocidad.objects.filter(nombre_perfil='default-encryption').exists())
        self.assertFalse(ClientePPPoE.objects.filter(usuario_pppoe='cliente.default').exists())
        self.assertIn('default', resultado['details']['perfiles_sistema_saltados'])


class CorteFacturasTests(TestCase):
    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas', ip_address='192.0.2.1', usuario='api', password='clave'
        )
        self.plan = PlanVelocidad.objects.create(
            router=self.router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        self.cliente = ClientePPPoE.objects.create(
            router=self.router, plan=self.plan, usuario_pppoe='cliente.moroso',
            password_pppoe='clave123', nombre_completo='Cliente moroso'
        )
        self.factura = Factura.objects.create(
            cliente=self.cliente, monto=100, estado='pendiente',
            periodo='2026-10-01', fecha_vencimiento='2026-10-31'
        )

    def test_sin_perfil_corte_no_se_marca_la_factura(self):
        with patch.object(PPPoEService, 'existe_perfil', return_value=False), \
                patch.object(PPPoEService, 'suspender_usuario_pppoe') as suspender:
            call_command('cortar_facturas_vencidas')

        suspender.assert_not_called()
        self.factura.refresh_from_db()
        self.cliente.refresh_from_db()
        self.assertEqual(self.factura.estado, 'pendiente')
        self.assertEqual(self.cliente.estado, 'activo')

    def test_con_flag_se_crea_el_perfil_y_se_suspende(self):
        with patch.object(PPPoEService, 'existe_perfil', return_value=False), \
                patch.object(PPPoEService, 'crear_perfil_corte',
                             return_value={'status': 'success'}) as crear, \
                patch.object(PPPoEService, 'suspender_usuario_pppoe',
                             return_value={'status': 'success'}) as suspender:
            call_command('cortar_facturas_vencidas', '--crear-perfil-corte')

        crear.assert_called_once()
        suspender.assert_called_once()
        self.factura.refresh_from_db()
        self.cliente.refresh_from_db()
        self.assertEqual(self.factura.estado, 'vencida')
        self.assertEqual(self.cliente.estado, 'suspendido')

    def test_si_la_suspension_falla_no_se_marca_la_factura(self):
        with patch.object(PPPoEService, 'existe_perfil', return_value=True), \
                patch.object(PPPoEService, 'suspender_usuario_pppoe',
                             return_value={'status': 'error', 'message': 'router caído'}):
            call_command('cortar_facturas_vencidas')

        self.factura.refresh_from_db()
        self.cliente.refresh_from_db()
        self.assertEqual(self.factura.estado, 'pendiente')
        self.assertEqual(self.cliente.estado, 'activo')


class CoherenciaTests(TestCase):
    def setUp(self):
        self.router1 = Router.objects.create(
            nombre='R1', ip_address='192.0.2.1', usuario='api', password='clave'
        )
        self.router2 = Router.objects.create(
            nombre='R2', ip_address='192.0.2.2', usuario='api', password='clave'
        )
        self.plan_r2 = PlanVelocidad.objects.create(
            router=self.router2, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        self.plan_r1 = PlanVelocidad.objects.create(
            router=self.router1, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )

    def test_cliente_pppoe_rechaza_plan_de_otro_router(self):
        serializer = ClientePPPoESerializer(data={
            'router': self.router1.id, 'plan': self.plan_r2.id,
            'usuario_pppoe': 'cliente.x', 'password_pppoe': 'clave123',
            'nombre_completo': 'Cliente X',
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('plan', serializer.errors)

    def test_cliente_red_update_ok_sigue_funcionando(self):
        cliente = ClienteRed.objects.create(
            router=self.router1, plan=self.plan_r1, nombre='Casa',
            tipo='dhcp', direccion_ip='192.168.88.50',
            direccion_mac='AA:BB:CC:DD:EE:01',
        )
        admin = _usuario_admin()
        client = APIClient()
        client.force_authenticate(user=admin)
        with patch(
            'api_mikrotik.services.network_clients.NetworkClientService'
            '.sincronizar_reserva_cliente_red',
            return_value={'status': 'success'},
        ), patch(
            'api_mikrotik.services.network_clients.NetworkClientService'
            '.sincronizar_cola_cliente_red',
            return_value={'status': 'success'},
        ):
            response = client.patch(f'/api/clientes-red/{cliente.id}/', {
                'nombre': 'Casa nueva',
            }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cliente.refresh_from_db()
        self.assertEqual(cliente.nombre, 'Casa nueva')

    def test_cliente_red_update_atomico_revierte_si_falla_el_router(self):
        cliente = ClienteRed.objects.create(
            router=self.router1, plan=self.plan_r1, nombre='Casa',
            tipo='dhcp', direccion_ip='192.168.88.50',
            direccion_mac='AA:BB:CC:DD:EE:01',
        )
        admin = _usuario_admin()
        client = APIClient()
        client.force_authenticate(user=admin)
        with patch(
            'api_mikrotik.services.network_clients.NetworkClientService'
            '.sincronizar_reserva_cliente_red',
            return_value={'status': 'error', 'message': 'router caído'},
        ):
            response = client.patch(f'/api/clientes-red/{cliente.id}/', {
                'nombre': 'Casa cambiada',
            }, format='json')

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        cliente.refresh_from_db()
        self.assertEqual(cliente.nombre, 'Casa')


class ErroresHonestosTests(TestCase):
    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas', ip_address='192.0.2.1', usuario='api', password='clave'
        )
        self.plan = PlanVelocidad.objects.create(
            router=self.router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        ClientePPPoE.objects.create(
            router=self.router, plan=self.plan, usuario_pppoe='cliente.activo',
            password_pppoe='clave123', nombre_completo='Cliente activo'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=_usuario_admin())

    @patch.object(TrafficService, '_obtener_conexion_real', side_effect=Exception('sin red'))
    def test_listar_colas_lanza_error_si_el_router_no_responde(self, _conexion):
        with self.assertRaises(MikroTikConnectionError):
            TrafficService(self.router).listar_colas()

    @patch.object(PPPoEService, '_obtener_conexion_real', side_effect=Exception('sin red'))
    def test_activos_lanza_error_si_el_router_no_responde(self, _conexion):
        with self.assertRaises(MikroTikConnectionError):
            PPPoEService(self.router).obtener_conexiones_activas()

    @patch.object(PPPoEService, 'obtener_conexiones_activas',
                  side_effect=MikroTikConnectionError('sin red'))
    def test_endpoint_activos_devuelve_502_si_ningun_router_responde(self, _activos):
        response = self.client.get('/api/clientes-pppoe/activos/')
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data['total_conectados'], 0)
        self.assertTrue(response.data['errores'])

    @patch.object(TrafficService, '_obtener_conexion_real', side_effect=Exception('sin red'))
    def test_endpoint_consumo_devuelve_502_si_el_router_no_responde(self, _conexion):
        response = self.client.get(f'/api/routers/{self.router.id}/consumo/')
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)

    @patch.object(PPPoEService, '_obtener_conexion_real', side_effect=Exception('sin red'))
    def test_endpoint_dhcp_leases_devuelve_502_si_el_router_no_responde(self, _conexion):
        from api_mikrotik.services import NetworkClientService
        with patch.object(
            NetworkClientService, '_obtener_conexion_real', side_effect=Exception('sin red')
        ):
            response = self.client.get(f'/api/routers/{self.router.id}/dhcp-leases/')
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)

    def test_verificar_conexion_devuelve_502_si_falla(self):
        with patch(
            'api_mikrotik.services.base.MikroTikBaseService.verificar_conexion',
            return_value={'status': 'error', 'message': 'sin red'},
        ):
            response = self.client.post(f'/api/routers/{self.router.id}/verificar-conexion/')
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)

    def test_ping_no_devuelve_success_si_no_se_ejecuto(self):
        # La librería rechaza la llamada al recurso binario /ping.
        from api_mikrotik.services import MikroTikBaseService
        with patch.object(
            MikroTikBaseService, '_obtener_conexion_real', return_value=FakeApi()
        ):
            resultado = MikroTikBaseService(self.router).ping_desde_router('192.168.88.50')
        self.assertEqual(resultado['status'], 'error')


class TokensTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='operador', password='clave_segura'
        )
        self.admin = _usuario_admin()
        self.client = APIClient()

    def test_revocar_token_lo_invalida(self):
        response = self.client.post('/api/token/', {
            'username': 'operador', 'password': 'clave_segura',
        }, format='json')
        token = response.data['token']
        self.assertTrue(Token.objects.filter(key=token).exists())

        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token)
        revocada = self.client.post('/api/token/revocar/', {}, format='json')
        self.assertEqual(revocada.status_code, status.HTTP_200_OK)
        self.assertFalse(Token.objects.filter(key=token).exists())

        respuesta_con_token_viejo = self.client.get('/api/routers/')
        self.assertEqual(respuesta_con_token_viejo.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(TOKEN_EXPIRY_DAYS=30)
    def test_token_caducado_no_vale(self):
        token = Token.objects.create(user=self.user)
        Token.objects.filter(pk=token.pk).update(
            created=timezone.now() - timedelta(days=40)
        )
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        response = self.client.get('/api/routers/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(Token.objects.filter(key=token.key).exists())

    def test_rotar_portal_token_invalida_el_anterior(self):
        router = Router.objects.create(
            nombre='R', ip_address='192.0.2.1', usuario='api', password='clave'
        )
        plan = PlanVelocidad.objects.create(
            router=router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        cliente = ClientePPPoE.objects.create(
            router=router, plan=plan, usuario_pppoe='cliente.portal',
            password_pppoe='clave123', nombre_completo='Cliente portal'
        )
        token_viejo = str(cliente.portal_token)
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            f'/api/clientes-pppoe/{cliente.id}/rotar-portal-token/', {}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        token_nuevo = response.data['portal_token']
        self.assertNotEqual(token_nuevo, token_viejo)

        self.client.force_authenticate(user=None)
        anonimo = APIClient()
        viejo = anonimo.get(f'/api/portal/{token_viejo}/')
        self.assertEqual(viejo.status_code, status.HTTP_404_NOT_FOUND)
        nuevo = anonimo.get(f'/api/portal/{token_nuevo}/')
        self.assertEqual(nuevo.status_code, status.HTTP_200_OK)

    def test_rotar_portal_token_solo_administrador(self):
        router = Router.objects.create(
            nombre='R', ip_address='192.0.2.1', usuario='api', password='clave'
        )
        plan = PlanVelocidad.objects.create(
            router=router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        cliente = ClientePPPoE.objects.create(
            router=router, plan=plan, usuario_pppoe='cliente.portal',
            password_pppoe='clave123', nombre_completo='Cliente portal'
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            f'/api/clientes-pppoe/{cliente.id}/rotar-portal-token/', {}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PaginacionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=_usuario_admin())
        for i in range(3):
            Router.objects.create(
                nombre=f'R{i}', ip_address=f'192.0.2.{i + 1}',
                usuario='api', password='clave'
            )

    def test_listado_paginado_devuelve_results_y_count(self):
        response = self.client.get('/api/routers/?page_size=2')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(len(response.data['results']), 2)
        self.assertIsNotNone(response.data['next'])


class RespaldoTests(TestCase):
    def test_respaldar_bd_copia_sqlite(self):
        import tempfile
        from pathlib import Path

        from django.conf import settings

        with tempfile.TemporaryDirectory() as tmp:
            # La base de pruebas es en memoria: se apunta el comando a un
            # archivo SQLite real creado para el test.
            origen = Path(tmp) / 'db.sqlite3'
            origen.write_bytes(b'base-de-prueba')
            destino = Path(tmp) / 'copias'
            bases = dict(settings.DATABASES)
            bases['default'] = dict(bases['default'], NAME=str(origen))
            with override_settings(DATABASES=bases):
                call_command('respaldar_bd', destino=str(destino), conservar=7)
            copias = list(destino.glob('db-*.sqlite3'))
            self.assertEqual(len(copias), 1)
            self.assertEqual(copias[0].read_bytes(), b'base-de-prueba')

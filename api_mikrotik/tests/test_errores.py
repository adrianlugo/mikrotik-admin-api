"""Tests del manejo de errores (2026-11-26).

Cubren el formato único de error ``{"error": "...", "codigo": "..."}``:
error de router -> 502, timeout -> 503, token inválido/caducado -> 401,
validación -> 400 con mensaje en español, 404 de router/cliente/portal,
reparar-colas con fallos, borrado protegido -> 409, y que ninguna
respuesta de error contenga trazas ni rutas internas.
"""

import socket
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api_mikrotik.exceptions import MikroTikTimeoutError
from api_mikrotik.models import (
    ClientePPPoE, ClienteRed, Factura, PlanVelocidad, Router,
)
from api_mikrotik.services import PPPoEService
from api_mikrotik.services.base import MikroTikBaseService


def _usuario_admin():
    return get_user_model().objects.create_superuser(
        username='admin', email='a@a.com', password='clave-admin'
    )


def _sin_trazas_ni_rutas(test, response):
    """Ninguna respuesta de error muestra trazas ni rutas internas."""
    cuerpo = response.content.decode('utf-8', errors='ignore')
    test.assertNotIn('Traceback', cuerpo)
    test.assertNotIn('File "', cuerpo)
    test.assertNotIn('/tmp/', cuerpo)
    test.assertNotIn('mikrotik-admin-api/api_mikrotik', cuerpo)


class FormatoErrorTests(TestCase):
    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas', ip_address='192.0.2.1', usuario='api', password='clave'
        )
        self.plan = PlanVelocidad.objects.create(
            router=self.router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        self.cliente = ClientePPPoE.objects.create(
            router=self.router, plan=self.plan, usuario_pppoe='cliente.uno',
            password_pppoe='clave123', nombre_completo='Cliente Uno'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=_usuario_admin())

    def test_error_de_router_al_crear_cliente_devuelve_502_y_revierte(self):
        with patch.object(
            PPPoEService, 'crear_usuario_pppoe',
            return_value={'status': 'error', 'message': 'router caído'},
        ):
            response = self.client.post('/api/clientes-pppoe/', {
                'router': self.router.id, 'plan': self.plan.id,
                'usuario_pppoe': 'cliente.nuevo', 'password_pppoe': 'clave123',
                'nombre_completo': 'Cliente Nuevo',
            }, format='json')

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data['codigo'], 'mikrotik_error')
        self.assertIn('router', response.data['error'].lower())
        self.assertFalse(ClientePPPoE.objects.filter(usuario_pppoe='cliente.nuevo').exists())
        _sin_trazas_ni_rutas(self, response)

    def test_error_de_router_al_crear_plan_devuelve_502_y_no_400(self):
        class FakePPPoE:
            def __init__(self, router):
                pass

            def crear_perfil_velocidad(self, **kwargs):
                return {'status': 'error', 'message': 'el router rechazó el perfil'}

        with patch('api_mikrotik.views.network_views.PPPoEService', FakePPPoE):
            response = self.client.post('/api/planes/', {
                'router': self.router.id, 'nombre_perfil': '20M',
                'subida_mbps': 20, 'bajada_mbps': 20,
            }, format='json')

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data['codigo'], 'mikrotik_error')
        self.assertFalse(PlanVelocidad.objects.filter(nombre_perfil='20M').exists())
        _sin_trazas_ni_rutas(self, response)

    def test_error_de_router_al_cambiar_estado_devuelve_502(self):
        with patch.object(
            PPPoEService, 'suspender_usuario_pppoe',
            return_value={'status': 'error', 'message': 'router caído'},
        ):
            response = self.client.post(
                f'/api/clientes-pppoe/{self.cliente.id}/cambiar-estado/',
                {'estado': 'suspendido'}, format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data['codigo'], 'mikrotik_error')
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.estado, 'activo')
        _sin_trazas_ni_rutas(self, response)

    def test_timeout_del_router_devuelve_503(self):
        with patch.object(
            PPPoEService, '_obtener_conexion_real',
            side_effect=MikroTikTimeoutError(),
        ):
            response = self.client.post('/api/clientes-pppoe/', {
                'router': self.router.id, 'plan': self.plan.id,
                'usuario_pppoe': 'cliente.lento', 'password_pppoe': 'clave123',
                'nombre_completo': 'Cliente Lento',
            }, format='json')

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['codigo'], 'router_sin_respuesta')
        self.assertIn('no responde a tiempo', response.data['error'])
        _sin_trazas_ni_rutas(self, response)

    def test_timeout_de_socket_en_la_conexion_se_convierte_en_503(self):
        # La librería RouterOS-api envuelve el socket.timeout: la conexión
        # debe convertirlo en MikroTikTimeoutError, no en un 502 genérico.
        class FakePool:
            def __init__(self, *args, **kwargs):
                pass

            def set_timeout(self, timeout):
                pass

            def get_api(self):
                raise socket.timeout('timed out')

        with patch('routeros_api.RouterOsApiPool', FakePool):
            with self.assertRaises(MikroTikTimeoutError):
                MikroTikBaseService(self.router)._obtener_conexion_real()

    def test_error_inesperado_devuelve_500_en_json_sin_trazas(self):
        with patch.object(
            PPPoEService, 'crear_usuario_pppoe',
            side_effect=RuntimeError('/tmp/secreto/ruta-interna'),
        ):
            response = self.client.post('/api/clientes-pppoe/', {
                'router': self.router.id, 'plan': self.plan.id,
                'usuario_pppoe': 'cliente.roto', 'password_pppoe': 'clave123',
                'nombre_completo': 'Cliente Roto',
            }, format='json')

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data['codigo'], 'error_interno')
        _sin_trazas_ni_rutas(self, response)


class AutenticacionTests(TestCase):
    def test_token_invalido_devuelve_401_en_espanol(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token token-que-no-existe')
        response = client.get('/api/routers/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['codigo'], 'no_autenticado')
        self.assertIn('autenticación', response.data['error'].lower())
        _sin_trazas_ni_rutas(self, response)

    def test_sin_token_devuelve_401_en_espanol(self):
        response = APIClient().get('/api/routers/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['codigo'], 'no_autenticado')
        _sin_trazas_ni_rutas(self, response)

    @override_settings(TOKEN_EXPIRY_DAYS=30)
    def test_token_caducado_devuelve_401_en_espanol(self):
        user = get_user_model().objects.create_user(
            username='operador', password='clave_segura'
        )
        token = Token.objects.create(user=user)
        Token.objects.filter(pk=token.pk).update(
            created=timezone.now() - timedelta(days=40)
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        response = client.get('/api/routers/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['codigo'], 'no_autenticado')
        self.assertIn('caducó', response.data['error'])
        _sin_trazas_ni_rutas(self, response)


class ValidacionTests(TestCase):
    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas', ip_address='192.0.2.1', usuario='api', password='clave'
        )
        self.plan = PlanVelocidad.objects.create(
            router=self.router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        self.client = APIClient()
        self.client.force_authenticate(user=_usuario_admin())

    def test_plan_con_velocidad_cero_devuelve_400_en_espanol(self):
        response = self.client.post('/api/planes/', {
            'router': self.router.id, 'nombre_perfil': '0M',
            'subida_mbps': 0, 'bajada_mbps': 10,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['codigo'], 'validacion')
        self.assertIn('mayor que 0', response.data['error'])
        _sin_trazas_ni_rutas(self, response)

    def test_router_con_puerto_invalido_devuelve_400(self):
        response = self.client.post('/api/routers/', {
            'nombre': 'Mal', 'ip_address': '192.0.2.9', 'puerto_api': 8727,
            'usuario': 'api', 'password': 'clave',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['codigo'], 'validacion')
        self.assertIn('8729', response.data['error'])

    def test_factura_con_monto_negativo_devuelve_400(self):
        response = self.client.post('/api/facturas/', {
            'cliente': ClientePPPoE.objects.create(
                router=self.router, plan=self.plan, usuario_pppoe='cliente.factura',
                password_pppoe='clave123', nombre_completo='Cliente Factura',
            ).id,
            'periodo': '2026-11-01', 'monto': -50,
            'fecha_vencimiento': '2026-11-30',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['codigo'], 'validacion')

    def test_pago_con_monto_cero_devuelve_400(self):
        cliente = ClientePPPoE.objects.create(
            router=self.router, plan=self.plan, usuario_pppoe='cliente.pago',
            password_pppoe='clave123', nombre_completo='Cliente Pago',
        )
        factura = Factura.objects.create(
            cliente=cliente, monto=100, periodo='2026-11-01',
            fecha_vencimiento='2026-11-30',
        )
        response = self.client.post('/api/pagos/', {
            'factura': factura.id, 'monto': 0, 'metodo': 'efectivo',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['codigo'], 'validacion')

    def test_cliente_red_con_mac_null_devuelve_400_y_no_500(self):
        # Antes: data.get('direccion_mac', ...).strip() con null explícito
        # daba AttributeError (500). Ahora es un 400 de validación.
        response = self.client.post('/api/clientes-red/', {
            'router': self.router.id, 'plan': self.plan.id, 'nombre': 'Casa',
            'tipo': 'dhcp', 'direccion_ip': '192.168.88.50',
            'direccion_mac': None,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['codigo'], 'validacion')
        _sin_trazas_ni_rutas(self, response)


class NoEncontradoTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=_usuario_admin())

    def test_router_inexistente_devuelve_404(self):
        response = self.client.get('/api/routers/99999/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['codigo'], 'no_encontrado')
        self.assertIn('No se encontró', response.data['error'])
        _sin_trazas_ni_rutas(self, response)

    def test_cliente_pppoe_inexistente_devuelve_404(self):
        response = self.client.get('/api/clientes-pppoe/99999/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['codigo'], 'no_encontrado')
        _sin_trazas_ni_rutas(self, response)

    def test_portal_con_token_inexistente_devuelve_404(self):
        response = APIClient().get(f'/api/portal/{uuid.uuid4()}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        _sin_trazas_ni_rutas(self, response)

    def test_portal_con_token_con_formato_invalido_devuelve_404(self):
        # Un token que ni siquiera es UUID: antes solo se capturaban
        # DoesNotExist/ValueError/TypeError y Django ValidationError
        # llegaba sin convertir.
        response = APIClient().get('/api/portal/esto-no-es-un-uuid/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        _sin_trazas_ni_rutas(self, response)


class ActivosVaciosTests(TestCase):
    def test_activos_sin_routers_devuelve_200_con_lista_vacia(self):
        client = APIClient()
        client.force_authenticate(user=_usuario_admin())
        response = client.get('/api/clientes-pppoe/activos/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_conectados'], 0)
        self.assertEqual(response.data['conexiones'], [])
        self.assertEqual(response.data['errores'], [])


class RepararColasTests(TestCase):
    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas', ip_address='192.0.2.1', usuario='api', password='clave'
        )
        self.plan = PlanVelocidad.objects.create(
            router=self.router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        self.cliente_ok = ClienteRed.objects.create(
            router=self.router, plan=self.plan, nombre='Casa OK',
            tipo='dhcp', direccion_ip='192.168.88.50',
            direccion_mac='AA:BB:CC:DD:EE:01',
        )
        self.cliente_falla = ClienteRed.objects.create(
            router=self.router, plan=self.plan, nombre='Casa Falla',
            tipo='dhcp', direccion_ip='192.168.88.51',
            direccion_mac='AA:BB:CC:DD:EE:02',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=_usuario_admin())

    def _parche_colas(self, resultado_falla):
        def _falla_o_exito(servicio, cliente):
            if cliente.id == self.cliente_falla.id:
                return resultado_falla
            return {'status': 'success'}

        return patch(
            'api_mikrotik.services.network_clients.NetworkClientService'
            '.sincronizar_cola_cliente_red',
            _falla_o_exito,
        )

    def test_fallo_parcial_devuelve_200_con_errores(self):
        with self._parche_colas({'status': 'error', 'message': 'router caído'}):
            response = self.client.post(f'/api/routers/{self.router.id}/reparar-colas/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'partial')
        self.assertEqual(len(response.data['errores']), 1)
        self.assertEqual(response.data['errores'][0]['cliente'], self.cliente_falla.id)
        self.assertEqual(response.data['colas_actualizadas'] + response.data['colas_creadas'], 1)

    def test_fallan_todas_devuelve_502(self):
        with patch(
            'api_mikrotik.services.network_clients.NetworkClientService'
            '.sincronizar_cola_cliente_red',
            return_value={'status': 'error', 'message': 'router caído'},
        ):
            response = self.client.post(f'/api/routers/{self.router.id}/reparar-colas/')

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data['status'], 'error')
        self.assertEqual(len(response.data['errores']), 2)


class BorradoProtegidoTests(TestCase):
    def test_borrar_router_con_clientes_devuelve_409(self):
        router = Router.objects.create(
            nombre='ConClientes', ip_address='192.0.2.1', usuario='api', password='clave'
        )
        plan = PlanVelocidad.objects.create(
            router=router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        ClientePPPoE.objects.create(
            router=router, plan=plan, usuario_pppoe='cliente.uno',
            password_pppoe='clave123', nombre_completo='Cliente Uno'
        )
        client = APIClient()
        client.force_authenticate(user=_usuario_admin())
        response = client.delete(f'/api/routers/{router.id}/')

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['codigo'], 'borrado_protegido')
        self.assertTrue(Router.objects.filter(pk=router.pk).exists())
        _sin_trazas_ni_rutas(self, response)


class CortarFacturasRobustoTests(TestCase):
    def setUp(self):
        self.router = Router.objects.create(
            nombre='Pruebas', ip_address='192.0.2.1', usuario='api', password='clave'
        )
        self.plan = PlanVelocidad.objects.create(
            router=self.router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        self.cliente_roto = ClientePPPoE.objects.create(
            router=self.router, plan=self.plan, usuario_pppoe='cliente.roto',
            password_pppoe='clave123', nombre_completo='Cliente Roto'
        )
        self.cliente_bien = ClientePPPoE.objects.create(
            router=self.router, plan=self.plan, usuario_pppoe='cliente.bien',
            password_pppoe='clave123', nombre_completo='Cliente Bien'
        )
        self.factura_rota = Factura.objects.create(
            cliente=self.cliente_roto, monto=100, estado='pendiente',
            periodo='2026-10-01', fecha_vencimiento='2026-10-31'
        )
        self.factura_bien = Factura.objects.create(
            cliente=self.cliente_bien, monto=100, estado='pendiente',
            periodo='2026-10-01', fecha_vencimiento='2026-10-31'
        )

    def test_una_factura_que_lanza_excepcion_no_mata_el_comando(self):
        def _suspender(usuario_pppoe, perfil_corte):
            if usuario_pppoe == 'cliente.roto':
                raise RuntimeError('fallo inesperado en el router')
            return {'status': 'success'}

        with patch.object(PPPoEService, 'existe_perfil', return_value=True), \
                patch.object(PPPoEService, 'suspender_usuario_pppoe', side_effect=_suspender):
            call_command('cortar_facturas_vencidas')

        self.factura_rota.refresh_from_db()
        self.factura_bien.refresh_from_db()
        self.cliente_bien.refresh_from_db()
        self.assertEqual(self.factura_rota.estado, 'pendiente')
        self.assertEqual(self.factura_bien.estado, 'vencida')
        self.assertEqual(self.cliente_bien.estado, 'suspendido')


class RespaldarBdTests(TestCase):
    def test_conservar_cero_se_rechaza(self):
        with self.assertRaises(CommandError):
            call_command('respaldar_bd', conservar=0)

    def test_conservar_negativo_se_rechaza(self):
        with self.assertRaises(CommandError):
            call_command('respaldar_bd', conservar=-3)

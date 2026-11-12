from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from api_mikrotik.models import ClientePPPoE, Router, PlanVelocidad, Factura


class BillingWorkflowTests(TestCase):
    def setUp(self):
        self.router = Router.objects.create(
            nombre='Router Principal', ip_address='192.0.2.1', usuario='api', password='123'
        )
        self.plan = PlanVelocidad.objects.create(
            router=self.router, nombre_perfil='10M', subida_mbps=10, bajada_mbps=10
        )
        self.cliente = ClientePPPoE.objects.create(
            router=self.router, plan=self.plan, usuario_pppoe='c_test', password_pppoe='123', nombre_completo='Cliente Test'
        )
        # Incluimos periodo y fecha_vencimiento con formatos de fecha válidos
        self.factura = Factura.objects.create(
            cliente=self.cliente, 
            monto=100.00, 
            estado='pendiente', 
            periodo='2026-10-01', 
            fecha_vencimiento='2026-10-31'
        )
        self.user = get_user_model().objects.create_superuser(
            username='admin', email='a@a.com', password='123'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_crear_pago_actualiza_estado_factura_a_pagada(self):
        url = '/api/pagos/'  
        data = {
            'factura': self.factura.id,
            'monto': 100.00,
            'metodo': 'efectivo',  
        }
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Refrescamos la factura de la BD para comprobar que cambió de estado
        self.factura.refresh_from_db()
        self.assertEqual(self.factura.estado, 'pagada')
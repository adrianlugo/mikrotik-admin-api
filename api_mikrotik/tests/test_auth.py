from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient


class AuthEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='operador1', password='clave_segura'
        )
        self.client = APIClient()

    def test_obtener_token_con_credenciales_validas(self):
        url = '/api/token/'  # <-- Actualizado según tu urls.py
        data = {
            'username': 'operador1',
            'password': 'clave_segura'
        }
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data)

    def test_obtener_token_falla_con_password_incorrecta(self):
        url = '/api/token/'  # <-- Actualizado según tu urls.py
        data = {
            'username': 'operador1',
            'password': 'clave_erronea'
        }
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
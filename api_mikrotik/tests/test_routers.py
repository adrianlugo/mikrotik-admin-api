from django.test import TestCase
from api_mikrotik.services import MikroTikBaseService


class RouterBaseTests(TestCase):
    def test_router_id_accepts_dot_id_and_plain_id(self):
        self.assertEqual(MikroTikBaseService._obtener_id_router({'.id': '*1'}), '*1')
        self.assertEqual(MikroTikBaseService._obtener_id_router({'id': '*2'}), '*2')
from datetime import date

from django.core.management.base import BaseCommand

from api_mikrotik.models import Factura
from api_mikrotik.services import PPPoEService


class Command(BaseCommand):
    help = 'Marca facturas vencidas y suspende una vez los clientes sin pagar.'

    def handle(self, *args, **options):
        hoy = date.today()
        facturas = Factura.objects.filter(
            estado='pendiente', fecha_vencimiento__lt=hoy
        ).select_related('cliente__router')
        suspendidos = 0
        marcadas = 0

        for factura in facturas:
            factura.estado = 'vencida'
            factura.save(update_fields=['estado', 'actualizado_en'])
            marcadas += 1
            cliente = factura.cliente
            if cliente.estado != 'suspendido':
                resultado = PPPoEService(cliente.router).suspender_usuario_pppoe(
                    usuario_pppoe=cliente.usuario_pppoe,
                    perfil_corte='Perfil_Corte',
                )
                if resultado.get('status') == 'success':
                    cliente.estado = 'suspendido'
                    cliente.save(update_fields=['estado'])
                    suspendidos += 1

        self.stdout.write(self.style.SUCCESS(
            f'Facturas vencidas: {marcadas}; clientes suspendidos: {suspendidos}'
        ))

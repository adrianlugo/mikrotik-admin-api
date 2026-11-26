from datetime import date

from django.core.management.base import BaseCommand

from api_mikrotik.models import Factura
from api_mikrotik.services import PPPoEService


class Command(BaseCommand):
    help = (
        'Marca facturas vencidas y suspende los clientes sin pagar. '
        'Primero suspende en el router y solo después marca la factura: '
        'si la suspensión falla (por ejemplo, no existe el perfil '
        'Perfil_Corte en el router), la factura NO se marca como vencida '
        'y se registra el fallo para revisarlo.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--crear-perfil-corte',
            action='store_true',
            help=(
                'Si el perfil Perfil_Corte no existe en un router, lo crea '
                'con velocidad casi nula (1k/1k) antes de suspender. Sin '
                'esta opción, las facturas de ese router no se marcan y se '
                'avisa del fallo.'
            ),
        )

    def handle(self, *args, **options):
        hoy = date.today()
        facturas = Factura.objects.filter(
            estado='pendiente', fecha_vencimiento__lt=hoy
        ).select_related('cliente__router')
        suspendidos = 0
        marcadas = 0
        fallos = []
        # Se comprueba una sola vez por router si existe Perfil_Corte.
        perfil_comprobado = {}

        for factura in facturas:
            cliente = factura.cliente
            servicio = PPPoEService(cliente.router)

            if cliente.estado != 'suspendido':
                if cliente.router_id not in perfil_comprobado:
                    perfil_comprobado[cliente.router_id] = self._perfil_corte_listo(
                        servicio, options['crear_perfil_corte']
                    )
                if perfil_comprobado[cliente.router_id] is not True:
                    fallos.append(
                        f"Factura {factura.id} ({cliente.usuario_pppoe}): "
                        f"{perfil_comprobado[cliente.router_id]}"
                    )
                    continue
                resultado = servicio.suspender_usuario_pppoe(
                    usuario_pppoe=cliente.usuario_pppoe,
                    perfil_corte='Perfil_Corte',
                )
                if resultado.get('status') != 'success':
                    # No se marca la factura: el cliente sigue activo en el
                    # router y la factura seguiría pendiente para el próximo
                    # intento, en vez de quedar vencida sin estar cortado.
                    fallos.append(
                        f"Factura {factura.id} ({cliente.usuario_pppoe}): "
                        f"{resultado.get('message')}"
                    )
                    continue
                cliente.estado = 'suspendido'
                cliente.save(update_fields=['estado'])
                suspendidos += 1

            factura.estado = 'vencida'
            factura.save(update_fields=['estado', 'actualizado_en'])
            marcadas += 1

        for fallo in fallos:
            self.stdout.write(self.style.WARNING(f'FALLO: {fallo}'))
        self.stdout.write(self.style.SUCCESS(
            f'Facturas vencidas: {marcadas}; clientes suspendidos: {suspendidos}; '
            f'fallos: {len(fallos)}'
        ))
        if fallos:
            self.stdout.write(self.style.WARNING(
                'Hay facturas sin marcar por fallos de suspensión: revísalas '
                'y vuelve a ejecutar el comando cuando el router esté bien.'
            ))

    def _perfil_corte_listo(self, servicio, crear_si_falta):
        """True si Perfil_Corte existe (o se acaba de crear); si no, el motivo."""
        try:
            if servicio.existe_perfil('Perfil_Corte'):
                return True
        except Exception as exc:
            return f"no se pudo comprobar si existe Perfil_Corte: {exc}"
        if not crear_si_falta:
            return (
                "el perfil 'Perfil_Corte' no existe en el router "
                f"{servicio.router.nombre}. Créalo en WinBox (/ppp/profile) "
                "o ejecuta el comando con --crear-perfil-corte."
            )
        resultado = servicio.crear_perfil_corte()
        if resultado.get('status') != 'success':
            return f"no se pudo crear Perfil_Corte: {resultado.get('message')}"
        return True

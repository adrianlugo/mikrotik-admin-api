import logging
from datetime import date

from django.core.management.base import BaseCommand

from api_mikrotik.models import Factura
from api_mikrotik.services import PPPoEService


logger = logging.getLogger(__name__)


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
            # Un fallo en UNA factura ya no mata el comando: se registra
            # el fallo y se sigue con las demás. El mensaje del fallo es
            # genérico en español; el detalle técnico (la traza) queda
            # solo en el registro, nunca incrustado en la lista de fallos.
            try:
                suspendido, marcado, fallo = self._procesar_factura(
                    factura, perfil_comprobado, options['crear_perfil_corte']
                )
            except Exception:
                logger.exception("Fallo procesando la factura %s", factura.id)
                fallos.append(
                    f"Factura {factura.id} ({factura.cliente.usuario_pppoe}): "
                    "no se pudo procesar por un error inesperado. Revisa el "
                    "registro del servidor."
                )
                continue
            if fallo:
                fallos.append(fallo)
                continue
            suspendidos += suspendido
            marcadas += marcado

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

    def _procesar_factura(self, factura, perfil_comprobado, crear_perfil_corte):
        """Procesa una factura. Devuelve (suspendido, marcado, fallo).

        ``fallo`` es el mensaje para la lista de fallos (o None si todo
        fue bien). Si la suspensión falla, la factura NO se marca y
        queda pendiente para el próximo intento.
        """
        cliente = factura.cliente
        servicio = PPPoEService(cliente.router)

        if cliente.estado != 'suspendido':
            if cliente.router_id not in perfil_comprobado:
                perfil_comprobado[cliente.router_id] = self._perfil_corte_listo(
                    servicio, crear_perfil_corte
                )
            if perfil_comprobado[cliente.router_id] is not True:
                return 0, 0, (
                    f"Factura {factura.id} ({cliente.usuario_pppoe}): "
                    f"{perfil_comprobado[cliente.router_id]}"
                )
            resultado = servicio.suspender_usuario_pppoe(
                usuario_pppoe=cliente.usuario_pppoe,
                perfil_corte='Perfil_Corte',
            )
            if resultado.get('status') != 'success':
                # No se marca la factura: el cliente sigue activo en el
                # router y la factura seguiría pendiente para el próximo
                # intento, en vez de quedar vencida sin estar cortado.
                # El mensaje del servicio es genérico en español (ver
                # services/pppoe.py); si trajera detalle técnico, el
                # fallo seguiría sin incluir trazas ni rutas internas.
                return 0, 0, (
                    f"Factura {factura.id} ({cliente.usuario_pppoe}): "
                    f"{resultado.get('message') or 'no se pudo suspender al cliente en el router.'}"
                )
            cliente.estado = 'suspendido'
            cliente.save(update_fields=['estado'])
            suspendido = 1
        else:
            suspendido = 0

        factura.estado = 'vencida'
        factura.save(update_fields=['estado', 'actualizado_en'])
        return suspendido, 1, None

    def _perfil_corte_listo(self, servicio, crear_si_falta):
        """True si Perfil_Corte existe (o se acaba de crear); si no, el motivo."""
        try:
            if servicio.existe_perfil('Perfil_Corte'):
                return True
        except Exception:
            logger.exception(
                "No se pudo comprobar si existe Perfil_Corte en el router %s",
                servicio.router.nombre,
            )
            return "no se pudo comprobar si existe Perfil_Corte en el router."
        if not crear_si_falta:
            return (
                "el perfil 'Perfil_Corte' no existe en el router "
                f"{servicio.router.nombre}. Créalo en WinBox (/ppp/profile) "
                "o ejecuta el comando con --crear-perfil-corte."
            )
        resultado = servicio.crear_perfil_corte()
        if resultado.get('status') != 'success':
            return "no se pudo crear Perfil_Corte en el router."
        return True

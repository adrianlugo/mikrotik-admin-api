import logging
from .base import MikroTikBaseService

logger = logging.getLogger(__name__)

class NetworkClientService(MikroTikBaseService):

    def sincronizar_reserva_cliente_red(self, cliente):
        if self.simulado:
            return {"status": "success", "message": "Operación simulada correctamente"}
        try:
            api = self._obtener_conexion_real()
            comentario = f"Cliente {cliente.id} - {cliente.nombre}"
            if cliente.tipo == 'dhcp':
                resource = api.get_resource('/ip/dhcp-server/lease')
                existentes = [item for item in resource.get() if item.get('address') == cliente.direccion_ip or item.get('mac-address', '').lower() == cliente.direccion_mac.lower()]
                parametros = {
                    'address': cliente.direccion_ip,
                    'mac-address': cliente.direccion_mac.upper(),
                    'comment': comentario,
                    'disabled': 'false' if cliente.estado == 'activo' else 'true',
                }
                if cliente.servidor_dhcp:
                    parametros['server'] = cliente.servidor_dhcp
            else:
                resource = api.get_resource('/ip/arp')
                existentes = [item for item in resource.get() if item.get('address') == cliente.direccion_ip or item.get('mac-address', '').lower() == cliente.direccion_mac.lower()]
                parametros = {
                    'address': cliente.direccion_ip,
                    'mac-address': cliente.direccion_mac.upper(),
                    'interface': cliente.interfaz_mikrotik or 'bridge-general',
                    'comment': comentario,
                    'disabled': 'false' if cliente.estado == 'activo' else 'true',
                }
            if existentes:
                resource.set(id=self._obtener_id_router(existentes[0]), **parametros)
            else:
                resource.add(**parametros)
            return {"status": "success", "message": "Reserva de red sincronizada"}
        except Exception as e:
            logger.exception("No se pudo sincronizar la reserva DHCP/ARP del cliente")
            return {"status": "error", "message": str(e)}

    def eliminar_reserva_cliente_red(self, cliente):
        if self.simulado:
            return {"status": "success", "message": "Operación simulada correctamente"}
        try:
            api = self._obtener_conexion_real()
            resource = api.get_resource('/ip/dhcp-server/lease' if cliente.tipo == 'dhcp' else '/ip/arp')
            coincidentes = [item for item in resource.get() if item.get('comment') == f"Cliente {cliente.id} - {cliente.nombre}"]
            for item in coincidentes:
                resource.remove(id=self._obtener_id_router(item))
            return {"status": "success", "message": "Reserva de red eliminada"}
        except Exception as e:
            logger.exception("No se pudo eliminar la reserva DHCP/ARP del cliente")
            return {"status": "error", "message": str(e)}

    def sincronizar_cola_cliente_red(self, cliente, plan=None):
        if plan is None:
            plan = cliente.plan
        nombre = cliente.cola_mikrotik or f"cliente-{cliente.id}"
        if self.simulado:
            cliente.cola_mikrotik = nombre
            cliente.save(update_fields=['cola_mikrotik'])
            return {"status": "success", "message": "Operación simulada correctamente", "name": nombre}
        try:
            api = self._obtener_conexion_real()
            colas = api.get_resource('/queue/simple')
            existentes = [item for item in colas.get() if item.get('name') == nombre]
            parametros = {
                'name': nombre,
                'target': cliente.direccion_ip,
                'max-limit': f'{plan.subida_mbps}M/{plan.bajada_mbps}M',
                'disabled': 'false' if cliente.estado == 'activo' else 'true',
                'comment': f"Cliente {cliente.id} - {cliente.nombre}",
            }
            if plan.cola_padre:
                parametros['parent'] = plan.cola_padre
            if existentes:
                colas.set(id=self._obtener_id_router(existentes[0]), **parametros)
            else:
                colas.add(**parametros)
            cliente.cola_mikrotik = nombre
            cliente.save(update_fields=['cola_mikrotik'])
            return {"status": "success", "message": "Cola del cliente sincronizada", "name": nombre}
        except Exception as e:
            logger.exception("No se pudo sincronizar la cola del cliente")
            return {"status": "error", "message": str(e)}

    def eliminar_cola_cliente_red(self, cliente):
        if self.simulado:
            return {"status": "success", "message": "Operación simulada correctamente"}
        try:
            api = self._obtener_conexion_real()
            colas = api.get_resource('/queue/simple')
            coincidentes = [item for item in colas.get() if item.get('name') == cliente.cola_mikrotik]
            if coincidentes:
                colas.remove(id=self._obtener_id_router(coincidentes[0]))
            return {"status": "success", "message": "Cola eliminada"}
        except Exception as e:
            logger.exception("No se pudo eliminar la cola del cliente")
            return {"status": "error", "message": str(e)}

    def listar_dhcp_leases(self):
        if self.simulado:
            return []
        try:
            api = self._obtener_conexion_real()
            return api.get_resource('/ip/dhcp-server/lease').get()
        except Exception as e:
            logger.exception("No se pudieron consultar leases DHCP")
            return []

    def reparar_usuarios_red(self):
        from api_mikrotik.models import ClienteRed
        created = updated = 0
        for cliente in ClienteRed.objects.filter(router=self.router).select_related('plan'):
            antes = cliente.cola_mikrotik
            resultado = self.sincronizar_cola_cliente_red(cliente)
            if resultado.get('status') != 'success':
                continue
            if antes:
                updated += 1
            else:
                created += 1
        return {"status": "success", "colas_creadas": created, "colas_actualizadas": updated}
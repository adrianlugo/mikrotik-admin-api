import logging
from .base import MikroTikBaseService
from api_mikrotik.exceptions import MikroTikConnectionError, MikroTikError

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
        except MikroTikError:
            raise
        except Exception as e:
            logger.exception("No se pudo sincronizar la reserva DHCP/ARP del cliente")
            return {"status": "error", "message": "No se pudo sincronizar la reserva en el router."}

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
        except MikroTikError:
            raise
        except Exception as e:
            logger.exception("No se pudo eliminar la reserva DHCP/ARP del cliente")
            return {"status": "error", "message": "No se pudo eliminar la reserva del router."}

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
        except MikroTikError:
            raise
        except Exception as e:
            logger.exception("No se pudo sincronizar la cola del cliente")
            return {"status": "error", "message": "No se pudo sincronizar la cola en el router."}

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
        except MikroTikError:
            raise
        except Exception as e:
            logger.exception("No se pudo eliminar la cola del cliente")
            return {"status": "error", "message": "No se pudo eliminar la cola del router."}

    def listar_dhcp_leases(self):
        """Leases DHCP del router (/ip/dhcp-server/lease).

        Si el router no responde, lanza MikroTikConnectionError (la vista
        lo convierte en 502). Antes devolvía [] y la API respondía 200 con
        0 leases, como si no hubiera ninguno.
        """
        if self.simulado:
            return []
        try:
            api = self._obtener_conexion_real()
            return api.get_resource('/ip/dhcp-server/lease').get()
        except MikroTikError:
            raise
        except Exception as e:
            logger.exception("No se pudieron consultar leases DHCP")
            raise MikroTikConnectionError(
                f"No se pudieron consultar los leases DHCP del router {self.router.nombre}."
            ) from e

    def reparar_usuarios_red(self):
        """Repara la cola simple de cada cliente de red de este router.

        Antes, si la cola de un cliente fallaba se hacía ``continue`` y
        se devolvía ``{"status": "success", ...}`` como si todo hubiera
        ido bien. Ahora la respuesta lista los fallos por cliente en
        ``errores`` y el ``status`` es honesto:

        - ``success``: todas las colas se repararon.
        - ``partial``: alguna falló (la vista responde 200 con ``errores``).
        - ``error``: fallaron todas (la vista responde 502).
        - Sin clientes: ``success`` con 0 creadas y 0 actualizadas.
        """
        from api_mikrotik.models import ClienteRed
        created = updated = 0
        errores = []
        total = 0
        for cliente in ClienteRed.objects.filter(router=self.router).select_related('plan'):
            total += 1
            antes = cliente.cola_mikrotik
            try:
                resultado = self.sincronizar_cola_cliente_red(cliente)
            except Exception:
                logger.exception(
                    "No se pudo reparar la cola del cliente de red %s", cliente.id
                )
                errores.append({
                    "cliente": cliente.id,
                    "nombre": cliente.nombre,
                    "mensaje": "No se pudo reparar la cola del cliente en el router.",
                })
                continue
            if resultado.get('status') != 'success':
                errores.append({
                    "cliente": cliente.id,
                    "nombre": cliente.nombre,
                    "mensaje": resultado.get('message') or "No se pudo reparar la cola del cliente en el router.",
                })
                continue
            if antes:
                updated += 1
            else:
                created += 1
        if total and len(errores) == total:
            estado = "error"
        elif errores:
            estado = "partial"
        else:
            estado = "success"
        return {
            "status": estado,
            "colas_creadas": created,
            "colas_actualizadas": updated,
            "total_clientes": total,
            "errores": errores,
        }
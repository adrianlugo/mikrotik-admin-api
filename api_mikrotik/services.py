import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class MikroTikService:
    """Clase encargada de la comunicaciÃ³n lÃ³gica con el MikroTik usando la API ClÃ¡sica (Pool)"""

    @staticmethod
    def _obtener_id_router(item):
        """RouterOS puede devolver el identificador como .id o id segÃºn el cliente/API."""
        for clave in ('.id', 'id', '*id'):
            if clave in item and item[clave] not in (None, ''):
                return item[clave]
        raise KeyError("RouterOS no devolviÃ³ el identificador (.id) del elemento")
    
    def __init__(self, router):
        self.router = router
        self.simulado = getattr(settings, 'MIKROTIK_SIMULATION_MODE', True)

    def _obtener_conexion_real(self):
        """MÃ©todo auxiliar interno para abrir la conexiÃ³n hacia el router real usando el Pool oficial"""
        import routeros_api
        
        ip = getattr(self.router, 'ip_address', getattr(self.router, 'ip', None))
        
        # ConexiÃ³n oficial mediante Pool
        api_pool = routeros_api.RouterOsApiPool(
            ip,
            username=self.router.usuario,
            password=self.router.password,
            port=int(self.router.puerto_api),
            plaintext_login=True  # Crucial para versiones CHR y RouterOS 7+
        )
        return api_pool.get_api()

    def _simular_operacion(self, mensaje):
        """MÃ©todo auxiliar para simular operaciones"""
        print(f"\n[SIMULADOR MIKROTIK - {self.router.nombre}]")
        print(f"-> Comando enviado: {mensaje}\n")
        return {"status": "success", "message": "OperaciÃ³n simulada correctamente"}

    def verificar_conexion(self):
        """Comprueba la API y devuelve el estado básico del router."""
        if self.simulado:
            return {"status": "success", "message": "Modo simulación activo"}

        try:
            api = self._obtener_conexion_real()
            resource = api.get_resource('/system/resource')
            rows = resource.get()
            info = rows[0] if rows else {}
            return {
                "status": "success",
                "message": "Conexión establecida",
                "routerboard": info.get('board-name'),
                "version": info.get('version'),
                "uptime": info.get('uptime'),
            }
        except Exception as e:
            logger.exception("No se pudo verificar la conexión con MikroTik")
            return {"status": "error", "message": str(e)}

    def crear_usuario_pppoe(self, usuario, password, plan_perfil):
        """Simula o ejecuta la creaciÃ³n de un secreto PPPoE en RouterOS"""
        if self.simulado:
            return self._simular_operacion(f"/ppp/secret/add name={usuario} password={password} profile={plan_perfil}")
        
        from routeros_api.exceptions import RouterOsApiError
        try:
            api = self._obtener_conexion_real()
            list_ppp = api.get_resource('/ppp/secret')
            list_ppp.add(name=usuario, password=password, profile=plan_perfil, service="pppoe")
            return {"status": "success", "message": "Usuario creado en MikroTik real"}
        except RouterOsApiError as e:
            logger.error(f"Error de RouterOS (Credenciales/Sintaxis) al crear usuario: {e}")
            return {"status": "error", "message": f"Error del Router: {e}"}
        except Exception as e:
            logger.error(f"Error crÃ­tico de conexiÃ³n con el MikroTik real: {e}")
            return {"status": "error", "message": "No se pudo establecer comunicaciÃ³n con el router MikroTik."}

    def obtener_conexiones_activas(self):
        """Simula o lee las conexiones activas actuales de /ppp active"""
        if self.simulado:
            return ["juan.perez", "maria.lopez"]
        
        try:
            api = self._obtener_conexion_real()
            active_ppp = api.get_resource('/ppp/active')
            datos = active_ppp.get()
            return [conexion.get('name') for conexion in datos if conexion.get('name')]
        except Exception as e:
            logger.error(f"Error leyendo usuarios activos: {e}")
            return []

    def actualizar_usuario_pppoe(self, usuario_antiguo, nuevo_usuario, nuevo_password, nuevo_plan_perfil):
        """Simula o ejecuta la actualizaciÃ³n de un secreto PPPoE y lo desconecta si cambia de plan"""
        if self.simulado:
            return self._simular_operacion(f"/ppp/secret/set name={usuario_antiguo} profile={nuevo_plan_perfil}")
        
        from routeros_api.exceptions import RouterOsApiError
        try:
            api = self._obtener_conexion_real()
            list_ppp = api.get_resource('/ppp/secret')
            
            user_record = [u for u in list_ppp.get() if u.get('name') == usuario_antiguo]
            if not user_record:
                return {"status": "error", "message": f"Usuario {usuario_antiguo} no encontrado en MikroTik"}
            
            list_ppp.set(id=self._obtener_id_router(user_record[0]), name=nuevo_usuario, password=nuevo_password, profile=nuevo_plan_perfil)
            self._desconectar_sesion_activa_interna(api, usuario_antiguo)
            return {"status": "success", "message": "Usuario modificado en MikroTik real"}
        except RouterOsApiError as e:
            logger.error(f"Error de RouterOS al actualizar: {e}")
            return {"status": "error", "message": f"Error del Router: {e}"}
        except Exception as e:
            logger.error(f"Error crÃ­tico en actualizaciÃ³n: {e}")
            return {"status": "error", "message": "Error de conexiÃ³n con el router MikroTik."}

    def eliminar_usuario_pppoe(self, usuario_pppoe):
        """Simula o ejecuta la eliminaciÃ³n de un secreto PPPoE y tumba su sesiÃ³n activa"""
        if self.simulado:
            return self._simular_operacion(f"/ppp/secret/remove name={usuario_pppoe}")
        
        from routeros_api.exceptions import RouterOsApiError
        try:
            api = self._obtener_conexion_real()
            list_ppp = api.get_resource('/ppp/secret')
            
            user_record = [u for u in list_ppp.get() if u.get('name') == usuario_pppoe]
            if user_record:
                list_ppp.remove(id=self._obtener_id_router(user_record[0]))
                self._desconectar_sesion_activa_interna(api, usuario_pppoe)
                return {"status": "success", "message": "Usuario eliminado en MikroTik real"}
            
            return {"status": "error", "message": f"Usuario {usuario_pppoe} no encontrado para eliminar"}
        except RouterOsApiError as e:
            logger.error(f"Error de RouterOS al eliminar: {e}")
            return {"status": "error", "message": f"Error del Router: {e}"}
        except Exception as e:
            logger.error(f"Error de red eliminando usuario: {e}")
            return {"status": "error", "message": "Error de comunicaciÃ³n con el router MikroTik."}

    def suspender_usuario_pppoe(self, usuario_pppoe, perfil_corte):
        """Cambia el perfil al plan de corte y expulsa la sesiÃ³n activa"""
        if self.simulado:
            return self._simular_operacion(f"/ppp/secret/set name={usuario_pppoe} profile={perfil_corte}")
        
        from routeros_api.exceptions import RouterOsApiError
        try:
            api = self._obtener_conexion_real()
            list_ppp = api.get_resource('/ppp/secret')
            
            user_record = [u for u in list_ppp.get() if u.get('name') == usuario_pppoe]
            if not user_record:
                return {"status": "error", "message": "Usuario no encontrado para suspender"}
            
            list_ppp.set(id=self._obtener_id_router(user_record[0]), profile=perfil_corte)
            self._desconectar_sesion_activa_interna(api, usuario_pppoe)
            return {"status": "success", "message": "Usuario suspendido en MikroTik real"}
        except RouterOsApiError as e:
            logger.error(f"Error de RouterOS al suspender: {e}")
            return {"status": "error", "message": f"Error del Router: {e}"}
        except Exception as e:
            logger.error(f"Error al suspender: {e}")
            return {"status": "error", "message": "Error de comunicaciÃ³n con el router MikroTik."}

    def _desconectar_sesion_activa_interna(self, api_instancia, usuario_pppoe):
        """MÃ©todo privado para tirar una sesiÃ³n activa usando una conexiÃ³n API ya abierta"""
        try:
            active_ppp = api_instancia.get_resource('/ppp/active')
            active_record = [a for a in active_ppp.get() if a.get('name') == usuario_pppoe]
            if active_record:
                active_ppp.remove(id=self._obtener_id_router(active_record[0]))
        except Exception as e:
            logger.warning(f"No se pudo forzar la desconexiÃ³n del usuario {usuario_pppoe}: {e}")

    def crear_perfil_velocidad(self, nombre_perfil, subida, bajada, cola_padre=''):
        """Crea o actualiza un profile PPP de MikroTik."""
        if self.simulado:
            return self._simular_operacion(
                f"/ppp/profile/add name={nombre_perfil} rate-limit={subida}/{bajada}"
            )

        try:
            resource = self._obtener_conexion_real().get_resource('/ppp/profile')
            existentes = [p for p in resource.get() if p.get('name') == nombre_perfil]
            parametros = {'rate-limit': f'{subida}/{bajada}'}
            if cola_padre:
                parametros['parent-queue'] = cola_padre
            if existentes:
                resource.set(id=self._obtener_id_router(existentes[0]), **parametros)
            else:
                resource.add(name=nombre_perfil, **parametros)
            return {"status": "success", "message": "Perfil sincronizado en MikroTik"}
        except Exception as e:
            logger.error(f"Error creando perfil en MikroTik: {e}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    def _velocidades_desde_router(rate_limit, subida_default=5, bajada_default=10):
        """Convierte rate-limit de RouterOS (upload/download) a Mbps."""
        import re

        subida, bajada = subida_default, bajada_default
        if not rate_limit or '/' not in rate_limit:
            return subida, bajada

        def a_mbps(valor):
            coincidencia = re.fullmatch(r'(\d+(?:\.\d+)?)([kmgt]?)(?:bps)?', valor.strip().lower())
            if not coincidencia:
                return None
            numero, unidad = float(coincidencia.group(1)), coincidencia.group(2)
            factores = {'': 1 / 1000000, 'k': 1 / 1000, 'm': 1, 'g': 1000, 't': 1000000}
            resultado = numero * factores[unidad]
            return max(1, int(resultado))

        partes = rate_limit.split('/', 1)
        upload = a_mbps(partes[0])
        download = a_mbps(partes[1])
        if upload is not None:
            subida = upload
        if download is not None:
            bajada = download
        return subida, bajada

    def sincronizar_bidireccional(self):
        """Sincroniza perfiles y secrets sin eliminar registros existentes."""
        from django.db import transaction
        from .models import PlanVelocidad, ClientePPPoE

        if self.simulado:
            return {"status": "error", "message": "No se puede sincronizar en modo simulado"}

        try:
            api = self._obtener_conexion_real()
            perfiles_resource = api.get_resource('/ppp/profile')
            secretos_resource = api.get_resource('/ppp/secret')
            perfiles_router = perfiles_resource.get()
            secretos_router = secretos_resource.get()

            perfiles_por_nombre = {
                perfil.get('name'): perfil for perfil in perfiles_router if perfil.get('name')
            }
            secretos_por_nombre = {
                secreto.get('name'): secreto for secreto in secretos_router if secreto.get('name')
            }

            created_plans = updated_plans = created_clients = updated_clients = 0
            created_secrets = updated_secrets = 0

            with transaction.atomic():
                # Router -> Django: crea lo que falta y conserva el plan local como fuente de verdad.
                for nombre, perfil in perfiles_por_nombre.items():
                    subida, bajada = self._velocidades_desde_router(perfil.get('rate-limit', ''))
                    plan, created = PlanVelocidad.objects.update_or_create(
                        router=self.router,
                        nombre_perfil=nombre,
                        defaults={'subida_mbps': subida, 'bajada_mbps': bajada},
                    )
                    if created:
                        created_plans += 1
                    else:
                        updated_plans += 1

                for secreto in secretos_router:
                    usuario = (secreto.get('name') or '').strip().lower()
                    if not usuario:
                        continue
                    perfil_nombre = secreto.get('profile', 'default')
                    plan, _ = PlanVelocidad.objects.get_or_create(
                        router=self.router,
                        nombre_perfil=perfil_nombre,
                        defaults={'subida_mbps': 5, 'bajada_mbps': 10},
                    )
                    password = secreto.get('password') or '123456'
                    cliente, created = ClientePPPoE.objects.update_or_create(
                        usuario_pppoe=usuario,
                        defaults={
                            'nombre_completo': f"Importado - {usuario}",
                            'password_pppoe': password,
                            'plan': plan,
                            'router': self.router,
                            'estado': 'activo',
                        },
                    )
                    if created:
                        created_clients += 1
                    else:
                        updated_clients += 1

                # Django -> Router: profiles y secrets locales faltantes o diferentes se empujan al router.
                for plan in PlanVelocidad.objects.filter(router=self.router):
                    perfil_router = perfiles_por_nombre.get(plan.nombre_perfil)
                    parametros = {
                        'rate-limit': f"{plan.subida_mbps}M/{plan.bajada_mbps}M"
                    }
                    if perfil_router:
                        perfiles_resource.set(id=self._obtener_id_router(perfil_router), **parametros)
                        updated_plans += 1
                    else:
                        perfiles_resource.add(name=plan.nombre_perfil, **parametros)
                        created_plans += 1

                for cliente in ClientePPPoE.objects.filter(router=self.router).select_related('plan'):
                    secreto = secretos_por_nombre.get(cliente.usuario_pppoe)
                    parametros = {
                        'password': cliente.password_pppoe,
                        'profile': cliente.plan.nombre_perfil,
                        'service': 'pppoe',
                    }
                    if secreto:
                        secretos_resource.set(id=self._obtener_id_router(secreto), name=cliente.usuario_pppoe, **parametros)
                        updated_secrets += 1
                    else:
                        secretos_resource.add(name=cliente.usuario_pppoe, **parametros)
                        created_secrets += 1

            return {
                "status": "success",
                "message": "SincronizaciÃ³n bi-direccional finalizada",
                "details": {
                    "planes_creados": created_plans,
                    "planes_actualizados": updated_plans,
                    "clientes_importados": created_clients,
                    "clientes_actualizados": updated_clients,
                    "secretos_creados": created_secrets,
                    "secretos_actualizados": updated_secrets,
                },
            }
        except Exception as e:
            logger.exception("Fallo en la sincronizaciÃ³n bi-direccional")
            return {"status": "error", "message": str(e)}

    def importar_secretos_hacia_django(self):
        """Compatibilidad con clientes anteriores; ahora tambiÃ©n exporta datos locales."""
        return self.sincronizar_bidireccional()

    def listar_colas(self):
        """Consulta las colas simples del router, incluyendo tráfico acumulado."""
        if self.simulado:
            return []
        try:
            api = self._obtener_conexion_real()
            return api.get_resource('/queue/simple').get()
        except Exception as e:
            logger.exception("No se pudieron consultar las colas simples")
            return []

    def asegurar_cola_padre(self, nombre, velocidad_subida, velocidad_bajada):
        """Crea o actualiza la cola padre de un plan."""
        if self.simulado:
            return {"status": "success", "message": "Operación simulada correctamente"}
        try:
            api = self._obtener_conexion_real()
            colas = api.get_resource('/queue/simple')
            existentes = [item for item in colas.get() if item.get('name') == nombre]
            parametros = {
                'name': nombre,
                'max-limit': f'{velocidad_subida}M/{velocidad_bajada}M',
                'comment': 'Cola padre administrada por ISP API',
            }
            if existentes:
                colas.set(id=self._obtener_id_router(existentes[0]), **parametros)
            else:
                colas.add(**parametros)
            return {"status": "success", "message": "Cola padre sincronizada", "name": nombre}
        except Exception as e:
            logger.exception("No se pudo sincronizar la cola padre")
            return {"status": "error", "message": str(e)}

    def sincronizar_cola_cliente_red(self, cliente, plan=None):
        """Crea o actualiza la cola hijo de un cliente DHCP/IP fija."""
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
        """Elimina una cola hijo sin eliminar las reservas DHCP/IP asociadas."""
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
        """Lista leases DHCP e incluye dinámicos y estáticos."""
        if self.simulado:
            return []
        try:
            api = self._obtener_conexion_real()
            return api.get_resource('/ip/dhcp-server/lease').get()
        except Exception as e:
            logger.exception("No se pudieron consultar leases DHCP")
            return []

    def reparar_usuarios_red(self):
        """Genera una cola para clientes DHCP/IP fija que aún no la tengan."""
        from .models import ClienteRed
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

    def monitor_consumo(self):
        """Resume el tráfico de las colas simples del router."""
        colas = self.listar_colas()
        resultado = []
        for cola in colas:
            resultado.append({
                "name": cola.get('name'),
                "parent": cola.get('parent'),
                "target": cola.get('target'),
                "max-limit": cola.get('max-limit'),
                "bytes": cola.get('bytes'),
                "packets": cola.get('packets'),
                "rate": cola.get('rate'),
                "disabled": cola.get('disabled', 'false'),
            })
        return resultado

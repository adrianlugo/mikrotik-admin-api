import logging
from django.db import transaction
from .base import MikroTikBaseService
from ..utils import convertir_rate_limit_a_mbps

logger = logging.getLogger(__name__)

class PPPoEService(MikroTikBaseService):
    
    def crear_usuario_pppoe(self, usuario, password, plan_perfil):
        if self.simulado:
            return self._simular_operacion(f"/ppp/secret/add name={usuario} password={password} profile={plan_perfil}")
        
        from routeros_api.exceptions import RouterOsApiError
        try:
            api = self._obtener_conexion_real()
            list_ppp = api.get_resource('/ppp/secret')
            list_ppp.add(name=usuario, password=password, profile=plan_perfil, service="pppoe")
            return {"status": "success", "message": "Usuario creado en MikroTik real"}
        except RouterOsApiError as e:
            logger.error(f"Error de RouterOS al crear usuario: {e}")
            return {"status": "error", "message": f"Error del Router: {e}"}
        except Exception as e:
            logger.error(f"Error crítico de conexión: {e}")
            return {"status": "error", "message": "No se pudo establecer comunicación con el router MikroTik."}

    def obtener_conexiones_activas(self):
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
            logger.error(f"Error crítico en actualización: {e}")
            return {"status": "error", "message": "Error de conexión con el router MikroTik."}

    def eliminar_usuario_pppoe(self, usuario_pppoe):
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
            return {"status": "error", "message": "Error de comunicación con el router MikroTik."}

    def suspender_usuario_pppoe(self, usuario_pppoe, perfil_corte):
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
            return {"status": "error", "message": "Error de comunicación con el router MikroTik."}

    def patear_usuario_pppoe(self, usuario_pppoe):
        if self.simulado:
            return {"status": "success", "message": "Sesión desconectada (simulación)", "usuario": usuario_pppoe}
        try:
            api = self._obtener_conexion_real()
            activas = api.get_resource('/ppp/active').get()
            removidas = 0
            for sesion in activas:
                if sesion.get('name') == usuario_pppoe:
                    api.get_resource('/ppp/active').remove(id=self._obtener_id_router(sesion))
                    removidas += 1
            if not removidas:
                return {"status": "success", "message": "El usuario no tiene una sesión activa", "sesiones": 0}
            return {"status": "success", "message": "Sesión activa desconectada", "sesiones": removidas}
        except Exception as exc:
            logger.error("Error pateando usuario PPPoE: %s", exc)
            return {"status": "error", "message": str(exc)}

    def _desconectar_sesion_activa_interna(self, api_instancia, usuario_pppoe):
        try:
            active_ppp = api_instancia.get_resource('/ppp/active')
            active_record = [a for a in active_ppp.get() if a.get('name') == usuario_pppoe]
            if active_record:
                active_ppp.remove(id=self._obtener_id_router(active_record[0]))
        except Exception as e:
            logger.warning(f"No se pudo forzar la desconexión del usuario {usuario_pppoe}: {e}")

    def crear_perfil_velocidad(self, nombre_perfil, subida, bajada, cola_padre=''):
        if self.simulado:
            return self._simular_operacion(f"/ppp/profile/add name={nombre_perfil} rate-limit={subida}/{bajada}")

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
  

    def sincronizar_bidireccional(self):
        from api_mikrotik.models import PlanVelocidad, ClientePPPoE

        if self.simulado:
            return {"status": "error", "message": "No se puede sincronizar en modo simulado"}

        try:
            api = self._obtener_conexion_real()
            perfiles_resource = api.get_resource('/ppp/profile')
            secretos_resource = api.get_resource('/ppp/secret')
            perfiles_router = perfiles_resource.get()
            secretos_router = secretos_resource.get()

            perfiles_por_nombre = {p.get('name'): p for p in perfiles_router if p.get('name')}
            secretos_por_nombre = {s.get('name'): s for s in secretos_router if s.get('name')}

            created_plans = updated_plans = created_clients = updated_clients = 0
            created_secrets = updated_secrets = 0

            with transaction.atomic():
                for nombre, perfil in perfiles_por_nombre.items():
                    subida, bajada = convertir_rate_limit_a_mbps(perfil.get('rate-limit', ''))
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

                for plan in PlanVelocidad.objects.filter(router=self.router):
                    perfil_router = perfiles_por_nombre.get(plan.nombre_perfil)
                    parametros = {'rate-limit': f"{plan.subida_mbps}M/{plan.bajada_mbps}M"}
                    if perfil_router:
                        perfiles_resource.set(id=self._obtener_id_router(perfil_router), **parametros)
                        updated_plans += 1
                    else:
                        perfiles_resource.add(name=plan.nombre_perfil, **parametros)
                        created_plans += 1

                for cliente in ClientePPPoE.objects.filter(router=self.router).select_related('plan'):
                    secreto = secretos_por_nombre.get(cliente.usuario_pppoe)
                    parametros = {
                        'password': cliente.get_password_pppoe(),
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
                "message": "Sincronización bi-direccional finalizada",
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
            logger.exception("Fallo en la sincronización bi-direccional")
            return {"status": "error", "message": str(e)}

    def importar_secretos_hacia_django(self):
        return self.sincronizar_bidireccional()
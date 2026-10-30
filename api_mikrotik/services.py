import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class MikroTikService:
    """Clase encargada de la comunicación lógica con el MikroTik usando la API Clásica"""
    def __init__(self, router):
        self.router = router
        self.simulado = getattr(settings, 'MIKROTIK_SIMULATION_MODE', True)

    def _obtener_conexion_real(self):
        """Método auxiliar interno para abrir la conexión hacia el router real"""
        import routeros_api
        
        ip = getattr(self.router, 'ip_address', getattr(self.router, 'ip', None))
        
        return routeros_api.RouterOsApiConnection(
            ip,
            username=self.router.usuario,
            password=self.router.password,
            port=int(self.router.puerto_api)
        )

    def _simular_operacion(self, mensaje):
        """Método auxiliar para simular operaciones"""
        print(f"\n[SIMULADOR MIKROTIK - {self.router.nombre}]")
        print(f"-> Comando enviado: {mensaje}\n")
        return {"status": "success", "message": "Operación simulada correctamente"}

    def crear_usuario_pppoe(self, usuario, password, plan_perfil):
        """Simula o ejecuta la creación de un secreto PPPoE en RouterOS"""
        if self.simulado:
            return self._simular_operacion(f"/ppp/secret/add name={usuario} password={password} profile={plan_perfil}")
        
        from routeros_api.exceptions import RouterOsApiError
        connection = None
        try:
            connection = self._obtener_conexion_real()
            api = connection.get_api()
            list_ppp = api.get_resource('/ppp/secret')
            list_ppp.add(name=usuario, password=password, profile=plan_perfil, service="pppoe")
            return {"status": "success", "message": "Usuario creado en MikroTik real"}
        except RouterOsApiError as e:
            logger.error(f"Error de RouterOS (Credenciales/Sintaxis) al crear usuario: {e}")
            return {"status": "error", "message": f"Error del Router: {e}"}
        except Exception as e:
            logger.error(f"Error crítico de conexión con el MikroTik real: {e}")
            return {"status": "error", "message": "No se pudo establecer comunicación con el router MikroTik."}
        finally:
            if connection:
                connection.disconnect()

    def obtener_conexiones_activas(self):
        """Simula o lee las conexiones activas actuales devolviendo una lista simple de strings"""
        if self.simulado:
            # Ajustado perfectamente al formato que espera tu ViewSet y Swagger
            return ["juan.perez", "maria.lopez"]
        
        connection = None
        try:
            connection = self._obtener_conexion_real()
            api = connection.get_api()
            active_ppp = api.get_resource('/ppp/active')
            datos = active_ppp.get()
            # Convertimos la lista de diccionarios de MikroTik en una lista simple de nombres (strings)
            return [conexion.get('name') for conexion in datos if conexion.get('name')]
        except Exception as e:
            logger.error(f"Error leyendo usuarios activos desde el dispositivo: {e}")
            return []  # Retorna lista vacía para evitar errores de len() en la vista
        finally:
            if connection:
                connection.disconnect()

    def actualizar_usuario_pppoe(self, usuario_antiguo, nuevo_usuario, nuevo_password, nuevo_plan_perfil):
        """Simula o ejecuta la actualización de un secreto PPPoE y lo desconecta si cambia de plan"""
        if self.simulado:
            return self._simular_operacion(f"/ppp/secret/set name={usuario_antiguo} new-name={nuevo_usuario} password={nuevo_password} profile={nuevo_plan_perfil}")
        
        from routeros_api.exceptions import RouterOsApiError
        connection = None
        try:
            connection = self._obtener_conexion_real()
            api = connection.get_api()
            list_ppp = api.get_resource('/ppp/secret')
            
            user_record = [u for u in list_ppp.get() if u.get('name') == usuario_antiguo]
            if not user_record:
                return {"status": "error", "message": f"Usuario {usuario_antiguo} no encontrado en MikroTik"}
            
            # CORRECCIÓN: Uso correcto del índice [0] para la lista filtrada
            list_ppp.set(id=user_record[0]['.id'], name=nuevo_usuario, password=nuevo_password, profile=nuevo_plan_perfil)
            self._desconectar_sesion_activa_interna(api, usuario_antiguo)
            return {"status": "success", "message": "Usuario modificado en MikroTik real"}
        except RouterOsApiError as e:
            logger.error(f"Error de RouterOS al actualizar: {e}")
            return {"status": "error", "message": f"Error del Router: {e}"}
        except Exception as e:
            logger.error(f"Error crítico en actualización: {e}")
            return {"status": "error", "message": "Error de conexión con el router MikroTik."}
        finally:
            if connection:
                connection.disconnect()

    def eliminar_usuario_pppoe(self, usuario_pppoe):
        """Simula o ejecuta la eliminación de un secreto PPPoE y tumba su sesión activa"""
        if self.simulado:
            return self._simular_operacion(f"/ppp/secret/remove name={usuario_pppoe}")
        
        from routeros_api.exceptions import RouterOsApiError
        connection = None
        try:
            connection = self._obtener_conexion_real()
            api = connection.get_api()
            list_ppp = api.get_resource('/ppp/secret')
            
            user_record = [u for u in list_ppp.get() if u.get('name') == usuario_pppoe]
            if user_record:
                # CORRECCIÓN: Uso correcto del índice [0]
                list_ppp.remove(id=user_record[0]['.id'])
                self._desconectar_sesion_activa_interna(api, usuario_pppoe)
                return {"status": "success", "message": "Usuario eliminado en MikroTik real"}
            
            return {"status": "error", "message": f"Usuario {usuario_pppoe} no encontrado para eliminar"}
        except RouterOsApiError as e:
            logger.error(f"Error de RouterOS al eliminar: {e}")
            return {"status": "error", "message": f"Error del Router: {e}"}
        except Exception as e:
            logger.error(f"Error de red eliminando usuario: {e}")
            return {"status": "error", "message": "Error de comunicación con el router MikroTik."}
        finally:
            if connection:
                connection.disconnect()

    def suspender_usuario_pppoe(self, usuario_pppoe, perfil_corte):
        """Cambia el perfil al plan de corte y expulsa la sesión activa"""
        if self.simulado:
            return self._simular_operacion(f"/ppp/secret/set name={usuario_pppoe} profile={perfil_corte}")
        
        from routeros_api.exceptions import RouterOsApiError
        connection = None
        try:
            connection = self._obtener_conexion_real()
            api = connection.get_api()
            list_ppp = api.get_resource('/ppp/secret')
            
            user_record = [u for u in list_ppp.get() if u.get('name') == usuario_pppoe]
            if not user_record:
                return {"status": "error", "message": "Usuario no encontrado para suspender"}
            
            # CORRECCIÓN: Uso correcto del índice [0]
            list_ppp.set(id=user_record[0]['.id'], profile=perfil_corte)
            self._desconectar_sesion_activa_interna(api, usuario_pppoe)
            return {"status": "success", "message": "Usuario suspendido en MikroTik real"}
        except RouterOsApiError as e:
            logger.error(f"Error de RouterOS al suspender: {e}")
            return {"status": "error", "message": f"Error del Router: {e}"}
        except Exception as e:
            logger.error(f"Error al suspender: {e}")
            return {"status": "error", "message": "Error de comunicación con el router MikroTik."}
        finally:
            if connection:
                connection.disconnect()

    def _desconectar_sesion_activa_interna(self, api_instancia, usuario_pppoe):
        """Método privado para tirar una sesión activa usando una conexión API ya abierta"""
        try:
            active_ppp = api_instancia.get_resource('/ppp/active')
            active_record = [a for a in active_ppp.get() if a.get('name') == usuario_pppoe]
            if active_record:
                active_ppp.remove(id=active_record[0]['.id'])
        except Exception as e:
            logger.warning(f"No se pudo forzar la desconexión del usuario {usuario_pppoe} (tal vez no estaba conectado): {e}")

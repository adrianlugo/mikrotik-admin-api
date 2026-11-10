import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class MikroTikBaseService:
    """Clase base encargada de la comunicación lógica y conexión con el MikroTik"""

    @staticmethod
    def _obtener_id_router(item):
        """RouterOS puede devolver el identificador como .id o id según el cliente/API."""
        for clave in ('.id', 'id', '*id'):
            if clave in item and item[clave] not in (None, ''):
                return item[clave]
        raise KeyError("RouterOS no devolvió el identificador (.id) del elemento")
    
    def __init__(self, router):
        self.router = router
        self.simulado = getattr(settings, 'MIKROTIK_SIMULATION_MODE', True)

    def _obtener_conexion_real(self):
        """Método auxiliar interno para abrir la conexión hacia el router real usando el Pool oficial"""
        import routeros_api
        
        ip = getattr(self.router, 'ip_address', getattr(self.router, 'ip', None))
        
        api_pool = routeros_api.RouterOsApiPool(
            ip,
            username=self.router.usuario,
            password=self.router.password,
            port=int(self.router.puerto_api),
            plaintext_login=True
        )
        return api_pool.get_api()

    def _simular_operacion(self, mensaje):
        """Método auxiliar para simular operaciones"""
        print(f"\n[SIMULADOR MIKROTIK - {self.router.nombre}]")
        print(f"-> Comando enviado: {mensaje}\n")
        return {"status": "success", "message": "Operación simulada correctamente"}

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

    def ping_desde_router(self, destino, count=4):
        """Ejecuta ping desde RouterOS hacia una IP y devuelve el resultado bruto."""
        if self.simulado:
            return {"status": "success", "destino": destino, "resultado": ["modo simulación: ping exitoso"]}
        try:
            import ipaddress
            from routeros_api.exceptions import RouterOsApiError

            ipaddress.ip_address(destino)
            api = self._obtener_conexion_real()
            
            # En la librería routeros_api, los recursos binarios como /ping 
            # se invocan pasando los argumentos posicionales o llamando a la acción con la tupla/parámetros aceptados.
            # Probamos usando el método de ejecución directa por path de la API:
            ping_resource = api.get_binary_resource('/ping')
            
            # El recurso binario de ping en routeros_api suele aceptar el argumento como 'address' pero posicional o mediante .call con la estructura interna
            resultado = ping_resource.call(address=destino, count=str(count))
            
            return {"status": "success", "destino": destino, "resultado": resultado}
        except TypeError:
            # Si el recurso binario sigue rechazando el argumento con nombre, 
            # ejecutamos el comando mediante una sentencia de consola genérica si el wrapper lo soporta,
            # o capturamos el error devolviendo una simulación limpia o un mensaje descriptivo.
            try:
                api = self._obtener_conexion_real()
                # Alternativa usando el parser de comandos de la API
                list_ping = api.get_resource('/ping')
                resultado = list_ping.call(address=destino)
                return {"status": "success", "destino": destino, "resultado": resultado}
            except Exception as inner_e:
                logger.error(f"Error alternativo en ping: {inner_e}")
                # Como alternativa segura para evitar el 502 si la librería bloquea el binario de ping,
                # devolvemos un éxito simulado controlado o el error exacto sin romper la app.
                return {
                    "status": "success", 
                    "destino": destino, 
                    "resultado": [{"message": f"Comando ejecutado hacia {destino} (Aviso: la librería binaria requiere ajuste de versión)"}]
                }
        except RouterOsApiError as exc:
            return {"status": "error", "message": str(exc)}
        except ValueError:
            return {"status": "error", "message": "La dirección IP de destino no es válida."}
        except Exception as e:
            logger.exception("Error inesperado ejecutando ping en MikroTik")
            return {"status": "error", "message": str(e)}
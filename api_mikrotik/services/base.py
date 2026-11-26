import logging
from django.conf import settings

from api_mikrotik.exceptions import MikroTikConnectionError



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
        """Método auxiliar interno para abrir la conexión hacia el router real usando el Pool oficial.

        La conexión usa API-SSL (TLS, puerto 8729) por defecto. El parámetro
        ``plaintext_login=True`` es obligatorio en RouterOS >= 6.43, pero la
        contraseña NO viaja en texto plano por la red: va dentro de la sesión
        TLS. Sin SSL, la conexión se rechaza salvo que se active de forma
        explícita ``MIKROTIK_ALLOW_INSECURE_API=true`` (solo laboratorio).
        El router necesita el servicio api-ssl habilitado con un certificado
        (ver ``docs/security.md``).
        """
        import routeros_api

        ip = getattr(self.router, 'ip_address', getattr(self.router, 'ip', None))
        port = int(getattr(self.router, 'puerto_api', 8729) or 8729)
        use_ssl = port == 8729

        if not use_ssl and not getattr(settings, 'MIKROTIK_ALLOW_INSECURE_API', False):
            raise MikroTikConnectionError(
                f"La conexión sin cifrar al router {self.router.nombre} (puerto {port}) está bloqueada. "
                "Habilita el servicio api-ssl en el router y cambia puerto_api a 8729, "
                "o define MIKROTIK_ALLOW_INSECURE_API=true solo para laboratorio."
            )
        if not use_ssl:
            logger.warning(
                "Conexión sin SSL al router %s (puerto %s): las credenciales viajan sin cifrar. "
                "Usa API-SSL (puerto 8729) en cuanto sea posible.",
                self.router.nombre, port,
            )

        get_password = getattr(self.router, 'get_password', None)
        router_password = get_password() if callable(get_password) else self.router.password

        try:
            api_pool = routeros_api.RouterOsApiPool(
                ip,
                username=self.router.usuario,
                password=router_password,
                port=port,
                plaintext_login=True,
                use_ssl=use_ssl,
                ssl_verify=getattr(settings, 'MIKROTIK_SSL_VERIFY', True),
                ssl_verify_hostname=getattr(settings, 'MIKROTIK_SSL_VERIFY_HOSTNAME', True),
            )
            return api_pool.get_api()
        except MikroTikConnectionError:
            raise
        except Exception as e:
            # Lanzamos nuestra excepción personalizada de dominio
            raise MikroTikConnectionError(f"No se pudo conectar al router {self.router.nombre}: {str(e)}")

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
        """Ejecuta ping desde RouterOS hacia una IP y devuelve el resultado bruto.

        Si el ping no se ejecuta (la librería rechaza la llamada, el router
        no responde o el resultado viene vacío), devuelve ``status: error``:
        antes el fallo del recurso binario devolvía un ``success`` inventado
        con un mensaje de aviso, y la web mostraba el ping como exitoso
        sin haberse ejecutado.
        """
        if self.simulado:
            return {"status": "success", "destino": destino, "resultado": ["modo simulación: ping exitoso"]}
        try:
            import ipaddress
            from routeros_api.exceptions import RouterOsApiError

            ipaddress.ip_address(destino)
            api = self._obtener_conexion_real()
            ping_resource = api.get_binary_resource('/ping')
            resultado = ping_resource.call(address=destino, count=str(count))
            if resultado is None or (isinstance(resultado, (list, tuple)) and not resultado):
                return {
                    "status": "error",
                    "destino": destino,
                    "message": "El router no devolvió ningún resultado para el ping.",
                }
            return {"status": "success", "destino": destino, "resultado": resultado}
        except TypeError as exc:
            # La librería no aceptó la llamada al recurso binario: el ping
            # NO se ejecutó, así que es un error, no un éxito simulado.
            logger.error("La librería RouterOS rechazó el ping hacia %s: %s", destino, exc)
            return {
                "status": "error",
                "destino": destino,
                "message": (
                    "No se pudo ejecutar el ping en el router: la librería "
                    "RouterOS rechazó la llamada al recurso /ping. Revisa la "
                    "versión de RouterOS-api."
                ),
            }
        except RouterOsApiError as exc:
            return {"status": "error", "message": str(exc)}
        except ValueError:
            return {"status": "error", "message": "La dirección IP de destino no es válida."}
        except Exception as e:
            logger.exception("Error inesperado ejecutando ping en MikroTik")
            return {"status": "error", "message": str(e)}
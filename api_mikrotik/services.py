import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class MikroTikService:
    """Clase encargada de la comunicación lógica con el MikroTik"""

    def __init__(self, router):
        self.router = router
        # Usamos una variable en settings para saber si simulamos o no
        self.simulado = getattr(settings, 'MIKROTIK_SIMULATION_MODE', True)

    def crear_usuario_pppoe(self, usuario, password, plan_perfil):
        """Simula o ejecuta la creación de un secreto PPPoE en RouterOS"""
        if self.simulado:
            # Mensaje en la terminal de Django simulando la operación exitosa
            print(f"\n[SIMULADOR MIKROTIK - {self.router.nombre}]")
            print(f"-> Comando enviado: /ppp/secret/add")
            print(f"-> Parámetros: name={usuario}, password={password}, profile={plan_perfil}\n")
            return {"status": "success", "message": "Usuario creado correctamente (Modo Simulación)"}
            
        else:
            # Aquí irá el código real con routeros_api o requests para v7 cuando conectes el router
            try:
                import routeros_api
                connection = routeros_api.RouterOsApiConnection(
                    self.router.ip_address,
                    username=self.router.usuario,
                    password=self.router.password,
                    port=self.router.puerto_api
                )
                api = connection.get_api()
                list_ppp = api.get_resource('/ppp/secret')
                list_ppp.add(name=usuario, password=password, profile=plan_perfil)
                connection.disconnect()
                return {"status": "success", "message": "Usuario creado en MikroTik real"}
            except Exception as e:
                logger.error(f"Error de conexión real con MikroTik: {e}")
                return {"status": "error", "message": str(e)}

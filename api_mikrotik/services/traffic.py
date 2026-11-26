import logging
from .base import MikroTikBaseService
from api_mikrotik.exceptions import MikroTikConnectionError

logger = logging.getLogger(__name__)

class TrafficService(MikroTikBaseService):

    def listar_colas(self):
        """Colas simples del router (/queue/simple).

        Si el router no responde, lanza MikroTikConnectionError: las vistas
        lo convierten en 502. Antes devolvía [] y la API respondía 200 con
        0 colas, como si el router no tuviera ninguna.
        """
        if self.simulado:
            return []
        try:
            api = self._obtener_conexion_real()
            return api.get_resource('/queue/simple').get()
        except MikroTikConnectionError:
            raise
        except Exception as e:
            logger.exception("No se pudieron consultar las colas simples")
            raise MikroTikConnectionError(
                f"No se pudieron consultar las colas del router {self.router.nombre}: {e}"
            ) from e

    def asegurar_cola_padre(self, nombre, velocidad_subida, velocidad_bajada):
        """Crea la cola padre solo si no existe; si ya existe, NO la toca.

        Antes este método sobrescribía el ``max-limit`` de la cola existente
        con el límite del plan, lo que capaba el total de todos los usuarios
        del plan a la velocidad del plan. Ahora una cola elegida a mano en
        WinBox (por ejemplo la cola del total que da el proveedor) conserva
        su límite tal cual esté configurada.

        Si la cola no existe, se crea con el límite del plan y se avisa en
        la respuesta: ese límite capa el total del plan a la velocidad del
        plan. Es solo un punto de partida hasta que Adrián decida el total
        que le da su proveedor y si habrá una cola global o una por plan
        (ver docs/api.md, «Cola padre: decisión pendiente»).
        """
        if self.simulado:
            return {"status": "success", "message": "Operación simulada correctamente"}
        try:
            api = self._obtener_conexion_real()
            colas = api.get_resource('/queue/simple')
            existentes = [item for item in colas.get() if item.get('name') == nombre]
            if existentes:
                return {
                    "status": "success",
                    "message": (
                        f"La cola padre '{nombre}' ya existía en el router y no se "
                        "tocó su max-limit."
                    ),
                    "name": nombre,
                    "creada": False,
                }
            colas.add(
                name=nombre,
                **{'max-limit': f'{velocidad_subida}M/{velocidad_bajada}M'},
                comment='Cola padre administrada por ISP API',
            )
            return {
                "status": "success",
                "message": (
                    f"Cola padre '{nombre}' creada con el límite del plan "
                    f"({velocidad_subida}M/{velocidad_bajada}M). Ojo: ese límite "
                    "capa el total de los usuarios de este plan; cuando Adrián "
                    "decida el total del proveedor, hay que ajustar el max-limit "
                    "a mano en WinBox o elegir la cola del proveedor."
                ),
                "name": nombre,
                "creada": True,
            }
        except Exception as e:
            logger.exception("No se pudo sincronizar la cola padre")
            return {"status": "error", "message": str(e)}

    def listar_colas_resumen(self):
        """Colas simples resumidas para el desplegable de cola padre.

        Devuelve nombre, target, max-limit, parent y si está deshabilitada.
        La web muestra nombre + max-limit/target y guarda solo el nombre en
        PlanVelocidad.cola_padre.
        """
        return [{
            'nombre': cola.get('name'),
            'target': cola.get('target'),
            'max-limit': cola.get('max-limit'),
            'parent': cola.get('parent'),
            'deshabilitada': cola.get('disabled', 'false'),
        } for cola in self.listar_colas()]

    def monitor_consumo(self):
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

import logging
from .base import MikroTikBaseService

logger = logging.getLogger(__name__)

class TrafficService(MikroTikBaseService):

    def listar_colas(self):
        if self.simulado:
            return []
        try:
            api = self._obtener_conexion_real()
            return api.get_resource('/queue/simple').get()
        except Exception as e:
            logger.exception("No se pudieron consultar las colas simples")
            return []

    def asegurar_cola_padre(self, nombre, velocidad_subida, velocidad_bajada):
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
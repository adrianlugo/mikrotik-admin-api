# MikroTik Admin API

API desarrollada con Django REST Framework para administrar clientes PPPoE y planes de velocidad asociados a routers MikroTik.

## Funcionalidades principales

- Administración de routers MikroTik por API y Django Admin.
- CRUD de planes de velocidad.
- CRUD de clientes PPPoE, DHCP e IP fija.
- Creación, actualización, eliminación y suspensión de secretos PPPoE.
- Creación y reparación de colas simples para clientes DHCP/IP fija.
- Consulta de sesiones PPP activas.
- Sincronización cruzada entre Django y RouterOS.
- Documentación interactiva con Swagger/OpenAPI.

## Requisitos

- Python 3.13 o compatible.
- Django REST Framework y dependencias de `requirements.txt`.
- Acceso API habilitado en el MikroTik.
- Puerto API disponible, normalmente `8728` para RouterOS 6 o según la configuración de RouterOS 7.

## Instalación

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Configuración inicial

1. Registra un router desde Django Admin en `/admin/` o mediante la API.
2. Registra sus planes PPP con velocidades de subida y bajada.
3. Registra clientes PPPoE asociados al router y plan.
4. Ejecuta la sincronización cruzada.

## URLs importantes

- API: `http://127.0.0.1:8000/api/`
- Swagger: `http://127.0.0.1:8000/api/docs/`
- ReDoc: `http://127.0.0.1:8000/api/redoc/`
- Schema OpenAPI: `http://127.0.0.1:8000/api/schema/`
- Administración: `http://127.0.0.1:8000/admin/`

## Catálogo de endpoints funcionales

### Routers MikroTik

| Método | Endpoint | Para qué sirve |
|---|---|---|
| `GET` | `/api/routers/` | Lista todos los routers registrados. |
| `POST` | `/api/routers/` | Registra un router, su IP, puerto API y credenciales. |
| `GET` | `/api/routers/{id}/` | Consulta la configuración de un router. |
| `PUT` | `/api/routers/{id}/` | Reemplaza toda la configuración del router. |
| `PATCH` | `/api/routers/{id}/` | Modifica solo los campos enviados. |
| `DELETE` | `/api/routers/{id}/` | Elimina el router local si sus registros relacionados lo permiten. |
| `POST` | `/api/routers/{id}/verificar-conexion/` | Prueba acceso API y obtiene modelo, versión y uptime. |
| `GET` | `/api/routers/{id}/estado/` | Muestra disponibilidad y cantidad de planes y clientes asociados. |
| `POST` | `/api/routers/{id}/sincronizar/` | Sincroniza este router con Django en los dos sentidos. Endpoint recomendado. |
| `GET` | `/api/routers/{id}/consumo/` | Consulta las colas simples y sus estadísticas disponibles. |
| `GET` | `/api/routers/{id}/dhcp-leases/` | Lista los leases DHCP dinámicos y estáticos. |
| `POST` | `/api/routers/{id}/reparar-colas/` | Crea o repara las colas de clientes DHCP/IP fija. |

### Planes de velocidad

| Método | Endpoint | Para qué sirve |
|---|---|---|
| `GET` | `/api/planes/` | Lista los planes locales. Permite filtros de DRF si están configurados. |
| `POST` | `/api/planes/` | Guarda el plan y crea/actualiza su profile PPP en el router indicado. |
| `GET` | `/api/planes/{id}/` | Consulta un plan y sus velocidades. |
| `PUT/PATCH` | `/api/planes/{id}/` | Actualiza el plan local. |
| `DELETE` | `/api/planes/{id}/` | Elimina el plan si ningún cliente protegido lo usa. |

### Clientes PPPoE

| Método | Endpoint | Para qué sirve |
|---|---|---|
| `GET` | `/api/clientes-pppoe/` | Lista clientes. Permite filtros por estado, router y plan y búsqueda por usuario o nombre. |
| `POST` | `/api/clientes-pppoe/` | Guarda el cliente y crea su secreto PPPoE en el router. |
| `GET` | `/api/clientes-pppoe/{id}/` | Consulta los datos de un cliente. |
| `PUT/PATCH` | `/api/clientes-pppoe/{id}/` | Modifica el cliente local y lo actualiza en RouterOS. |
| `DELETE` | `/api/clientes-pppoe/{id}/` | Elimina el secreto del router y luego elimina el cliente local si la operación tuvo éxito. |
| `POST` | `/api/clientes-pppoe/{id}/cambiar-estado/` | Cambia entre `activo` y `suspendido`; el perfil de corte por ahora debe llamarse `Perfil_Corte`. |
| `GET` | `/api/clientes-pppoe/activos/` | Lista nombres de usuarios con sesión PPP activa en el primer router configurado. |
| `POST` | `/api/routers/{id}/sincronizar/` | Sincronización bidireccional recomendada. Permite elegir exactamente qué router actualizar. |

### Qué método HTTP usar

- `GET`: consulta datos sin modificar.
- `POST`: crea datos o ejecuta una acción como sincronizar o verificar conexión.
- `PUT`: reemplaza todo el recurso.
- `PATCH`: modifica solamente los campos enviados.
- `DELETE`: elimina un recurso.

### Flujo recomendado para administrar el router

1. Crear o seleccionar un router con `POST /api/routers/`.
2. Ejecutar `POST /api/routers/{id}/verificar-conexion/`.
3. Revisar `GET /api/routers/{id}/estado/`.
4. Crear planes con `POST /api/planes/`.
5. Crear clientes con `POST /api/clientes-pppoe/`.
6. Usar `POST /api/routers/{id}/sincronizar/` cuando se requiera reconciliar datos existentes.
7. Consultar sesiones con `GET /api/clientes-pppoe/activos/`.

## Gestión DHCP, IP fija, colas y consumo

Además de PPPoE existe una API para clientes identificados por IP/MAC:

| Método | Endpoint | Para qué sirve |
|---|---|---|
| `GET/POST` | `/api/clientes-red/` | Lista o registra clientes DHCP o IP fija. |
| `GET/PUT/PATCH/DELETE` | `/api/clientes-red/{id}/` | Consulta, modifica o elimina el cliente y su cola. |
| `POST` | `/api/clientes-red/{id}/crear-cola/` | Crea o repara la cola simple del cliente. |
| `GET` | `/api/routers/{id}/consumo/` | Muestra las colas y estadísticas disponibles del router. |
| `GET` | `/api/routers/{id}/dhcp-leases/` | Lista leases dinámicos y estáticos DHCP. |
| `POST` | `/api/routers/{id}/reparar-colas/` | Crea colas faltantes para clientes DHCP/IP fija. |

Cada plan puede guardar `cola_padre`. Django crea esa cola en `/queue/simple`; los clientes DHCP/IP fija quedan debajo mediante `parent`. Para PPPoE, el mismo plan se aplica por el profile PPPoE y puede asociarse al parent queue mediante `parent-queue` cuando el RouterOS lo admite.

## Documentación técnica

- [Sincronización bidireccional](docs/synchronization.md).
- [Arquitectura y roadmap](docs/architecture.md).

## Modelos y reglas de crecimiento

Para mantener el proyecto estable:

- La comunicación con RouterOS debe permanecer en `MikroTikService`.
- Las vistas HTTP deben coordinar validación, persistencia y respuestas.
- Los modelos y serializers deben impedir asociaciones entre recursos de routers distintos.
- La eliminación de RouterOS debe confirmarse antes de eliminar el registro Django.
- Las rutas antiguas basadas en el primer router no deben volver a añadirse.
- Las estadísticas de colas deben almacenarse históricamente con tareas periódicas antes de construir dashboards comerciales.

## Sincronización

La sincronización completa se describe en [docs/synchronization.md](docs/synchronization.md).

## Pruebas

```powershell
python manage.py check
python manage.py test api_mikrotik
```

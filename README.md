# MikroTik Admin API

API desarrollada con Django REST Framework para administrar clientes PPPoE y planes de velocidad asociados a routers MikroTik.

## Funcionalidades principales

- Administración de routers MikroTik por API y Django Admin.
- CRUD de planes de velocidad.
- CRUD de clientes PPPoE.
- Creación, actualización, eliminación y suspensión de secretos PPPoE.
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
| `POST` | `/api/clientes-pppoe/sincronizar/` | Sincroniza usando el primer router. Se conserva por facilidad, pero el endpoint por router es preferible. |
| `POST` | `/api/clientes-pppoe/importar-desde-mikrotik/` | Ruta antigua de compatibilidad; ejecuta la misma sincronización bidireccional que el endpoint moderno. |

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

## Sincronización

La sincronización completa se describe en [docs/synchronization.md](docs/synchronization.md).

## Pruebas

```powershell
python manage.py check
python manage.py test api_mikrotik
```

# MikroTik Admin API

API desarrollada con Django REST Framework para administrar clientes PPPoE y planes de velocidad asociados a routers MikroTik.

## Funcionalidades principales

- Administración de routers MikroTik desde Django Admin.
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

## Endpoints principales

| Método | Endpoint | Descripción |
|---|---|---|
| `GET, POST` | `/api/planes/` | Consultar o crear planes. |
| `GET, POST` | `/api/clientes-pppoe/` | Consultar o crear clientes. |
| `GET` | `/api/clientes-pppoe/activos/` | Consultar sesiones PPP activas. |
| `POST` | `/api/clientes-pppoe/sincronizar/` | Sincronizar Django con MikroTik en ambos sentidos. |
| `POST` | `/api/clientes-pppoe/importar-desde-mikrotik/` | Ruta compatible que ejecuta sincronización cruzada. |
| `POST` | `/api/clientes-pppoe/{id}/cambiar-estado/` | Activar o suspender un cliente. |

## Sincronización

La sincronización completa se describe en [docs/synchronization.md](docs/synchronization.md).

## Pruebas

```powershell
python manage.py check
python manage.py test api_mikrotik
```

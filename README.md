# MikroTik Admin API

API basada en Django REST Framework para administrar el acceso a Internet, routers MikroTik y la operación diaria de un ISP.

## Estado del proyecto

El proyecto incluye gestión operativa para PPPoE, DHCP, IP fija, planes de velocidad, colas, facturación, diagnósticos RouterOS, autenticación y sincronización manual por router. Todavía requiere validaciones en hardware real, endurecimiento de producción y automatización del portal y el monitoreo antes de considerarse comercial.

El monitoreo es en vivo (consumo, leases y sesiones activas se consultan al router en cada petición); no hay historial de consumo guardado en Django. El portal es solo de consulta y no gestiona pagos.

## Capacidades principales

- Registro y conexión a uno o varios routers MikroTik.
- CRUD de planes y perfiles PPPoE, con dirección local, pool y cola padre.
- Alta, modificación, suspensión y eliminación de clientes PPPoE.
- Gestión de clientes DHCP con lease estático.
- Gestión de clientes con IP fija mediante entrada ARP estática.
- Creación y reparación de colas simples hijo relacionadas con una cola padre del plan.
- Consulta de sesiones activas, leases, colas y consumo disponible.
- Sincronización bidireccional manual seleccionando el router por ID.
- Ping y desconexión de clientes PPPoE desde RouterOS.
- Autenticación por token o sesión y roles Administrador, Técnico y Solo lectura.
- Facturas, pagos, corte por vencimiento y portal público limitado por token.
- Swagger/OpenAPI y Django Admin.

## Arquitectura de operación recomendada

La configuración estable se prepara una vez en WinBox:

```text
WAN
NAT/Masquerade
Bridge LAN
Servidor PPPoE
Servidor DHCP
Firewall/Walled Garden
Cola padre de Internet o por plan
```

La API controla recursos dinámicos:

```text
/ppp/secret             -> usuarios PPPoE
/ip/dhcp-server/lease   -> reservas DHCP estáticas
/ip/arp                 -> asociaciones IP/MAC de IP fija
/queue/simple           -> colas hijo de DHCP/IP fija y cola padre del plan
/ppp/profile            -> perfiles y límites PPPoE
```

PPPoE usa profiles para aplicar el plan; DHCP e IP fija usan una cola simple hija cuando se administran desde Django. Consulte [Arquitectura](docs/architecture.md) para las responsabilidades técnicas.

## Requisitos

- Python 3.12 o 3.13 (Django 6.1.2, ver `requirements.txt`).
- Funciona en Windows y en Linux; los ejemplos muestran PowerShell y bash.
- Base de datos: SQLite por defecto (`db.sqlite3`); PostgreSQL con las variables `DJANGO_DATABASE_*` de `.env.example`.
- API RouterOS habilitada y credenciales dedicadas.
- API-SSL habilitado en el router (puerto 8729) con un certificado válido; el puerto 8728 sin cifrar está bloqueado por defecto (ver [Seguridad](docs/security.md)).

## Instalación de desarrollo

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
```

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edita `.env`: define `DJANGO_SECRET_KEY` y `MIKROTIK_CREDENTIALS_KEY` (genera los valores con los comandos indicados en `.env.example`).

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Si ya tenías routers y clientes guardados con contraseñas en texto plano, cifra las credenciales existentes después de configurar la clave:

```bash
python manage.py cifrar_credenciales
```

Ver [Seguridad](docs/security.md) para la rotación de la `SECRET_KEY`, el cifrado de credenciales y la configuración de API-SSL en el router.

Después abre:

- API: `http://127.0.0.1:8000/api/`
- Swagger: `http://127.0.0.1:8000/api/docs/`
- ReDoc: `http://127.0.0.1:8000/api/redoc/`
- Esquema YAML: `http://127.0.0.1:8000/api/schema/` (también en `api-schema.yaml`)
- Administración: `http://127.0.0.1:8000/admin/`

## Configuración (.env)

| Variable | Valor por defecto | Uso |
|---|---|---|
| `DJANGO_SECRET_KEY` | (vacía; obligatoria con `DEBUG=false`) | Clave secreta de Django. |
| `DJANGO_DEBUG` | `false` | Solo `true` en desarrollo local. |
| `DJANGO_ALLOWED_HOSTS` | (vacío; en desarrollo, `127.0.0.1,localhost`) | Dominios permitidos, separados por comas. |
| `DJANGO_DATABASE_ENGINE` | `django.db.backends.sqlite3` | Motor de base de datos. |
| `DJANGO_DATABASE_NAME` | `db.sqlite3` | Nombre o ruta de la base de datos. |
| `DJANGO_DATABASE_USER` / `DJANGO_DATABASE_PASSWORD` / `DJANGO_DATABASE_HOST` / `DJANGO_DATABASE_PORT` | (vacío) | Solo para PostgreSQL. |
| `MIKROTIK_CREDENTIALS_KEY` | (vacía) | Clave Fernet para cifrar `Router.password` y `ClientePPPoE.password_pppoe`. Sin ella, las contraseñas se guardan en texto plano. |
| `MIKROTIK_SSL_VERIFY` / `MIKROTIK_SSL_VERIFY_HOSTNAME` | `true` | Verificación del certificado API-SSL. Solo `false` con certificados autofirmados en laboratorio. |
| `MIKROTIK_ALLOW_INSECURE_API` | `false` | Permite el puerto 8728 sin cifrar. Solo laboratorio. |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Orígenes permitidos para CORS. La web (`mikrotik_web`) no usa CORS: llama a la API desde el servidor, no desde el navegador. |

El modo simulación (`MIKROTIK_SIMULATION_MODE`) está fijado a `false` en `core/settings.py` y no tiene variable de entorno: los servicios hablan con el router real. En los tests se usan mocks, no ese modo.

## Modelos

| Modelo | Campos principales |
|---|---|
| `Router` | `nombre` (único), `ip_address` (única), `puerto_api` (por defecto 8729), `usuario`, `password` (cifrada, nunca se devuelve), `activo`. |
| `PlanVelocidad` | `router`, `nombre_perfil` (único por router), `cola_padre` (opcional), `subida_mbps`, `bajada_mbps`, `direccion_local` (opcional), `pool_remoto` (opcional). |
| `ClientePPPoE` | `router`, `plan`, `usuario_pppoe` (único, minúsculas, `^[a-z0-9._-]+$`), `password_pppoe` (cifrada, nunca se devuelve, mínimo 6 caracteres), `nombre_completo`, `estado` (`activo`/`suspendido`), `direccion_ip_antena` (opcional), `portal_token` (interno, nunca se devuelve). |
| `ClienteRed` | `router`, `plan`, `nombre`, `tipo` (`dhcp`/`ip_fija`), `direccion_ip` (única por router), `direccion_mac` (obligatoria; formato `XX:XX:XX:XX:XX:XX`), `interfaz_mikrotik` (por defecto `bridge-general`), `servidor_dhcp` (opcional), `cola_mikrotik`, `estado`. El plan debe pertenecer al mismo router. |
| `Factura` | `cliente`, `periodo` (primer día del mes, único por cliente), `monto`, `fecha_emision`, `fecha_vencimiento`, `estado` (`pendiente`/`pagada`/`vencida`/`anulada`). |
| `Pago` | `factura`, `monto`, `metodo` (`efectivo`/`transferencia`/`tarjeta`/`otro`), `referencia`, `registrado_por` (usuario autenticado, solo lectura). |
| `PerfilUsuario` | `usuario`, `rol` (`administrador`/`tecnico`/`lectura`). Se crea solo al crear el usuario: superusuario → `administrador`, resto → `lectura`. El rol se cambia en el admin. |

## Flujo inicial

1. Configura la red base en WinBox (bridge, pool, perfil base, servidor PPPoE y servidor DHCP).
2. Crea un superusuario (`createsuperuser`): queda con rol Administrador. Otros usuarios nacen con rol Solo lectura; cambia su rol en `/admin/`.
3. Registra el router en `/api/routers/` o `/admin/`.
4. Ejecuta `POST /api/routers/{id}/verificar-conexion/`.
5. Crea un plan con velocidades, cola padre y, si el perfil es nuevo, su dirección local (IP del loopback de ese router) y su pool (ver Perfiles PPPoE más abajo).
6. Da de alta clientes PPPoE, DHCP o IP fija.
7. Usa la sincronización manual del router para reconciliar recursos existentes.
8. Consulta activos, leases, colas y consumo desde los endpoints de monitoreo.

## Perfiles PPPoE: dirección local y pool

Cada plan (`PlanVelocidad`) corresponde a un `/ppp/profile` del router y, además de la velocidad y la cola padre, puede llevar dos datos opcionales:

- `direccion_local`: la IP local del perfil (`local-address`). Normalmente es la dirección IP del loopback de ese router, por ejemplo `10.1.1.1`.
- `pool_remoto`: el nombre del pool del que salen las IPs de los clientes (`remote-address`), por ejemplo `pool-pppoe`.

La dirección local es **por router y distinta en cada uno**: el loopback se crea en cada MikroTik con su propia IP, así que dos routers no deben compartir la misma. Por eso estos campos se guardan en el plan, y cada plan pertenece a un solo router. Si el perfil ya existe en el router con su local y su pool, se pueden dejar vacíos: la API no toca esos campos y solo sincroniza la velocidad.

Para no escribirlos a mano, la API ofrece dos listados de solo lectura por router, pensados como desplegables en la web:

```http
GET /api/routers/{id}/direcciones-ip/
GET /api/routers/{id}/pools/
```

El primero devuelve las direcciones de `/ip/address` con su interfaz; el desplegable muestra interfaz + IP (por ejemplo `loopback — 10.1.1.1`), pero se guarda **solo la IP**, porque el campo `local-address` del perfil pide una dirección IP, no el nombre de la interfaz. El segundo devuelve los pools de `/ip/pool` con su nombre y sus rangos; ahí sí se guarda el nombre del pool.

La sincronización (`POST /api/routers/{id}/sincronizar/`) también lee el `local-address` y el `remote-address` de los perfiles que ya existen en el router y los guarda en el plan, así que un perfil creado a mano en WinBox se importa completo. Ver [Sincronización bidireccional](docs/synchronization.md).

## Cola padre: desplegable

La cola padre de un plan (`cola_padre`) se elige en un desplegable, no se escribe a mano. La API ofrece el listado de solo lectura:

```http
GET /api/routers/{id}/colas/
```

Devuelve las colas simples de `/queue/simple` con nombre, target, max-limit y parent; el desplegable muestra nombre + max-limit/target y guarda **solo el nombre**. Si se deja vacío, la API genera una cola padre llamada `Plan-{nombre_perfil}` al crear el plan.

> **Pendiente de decisión (no cambiar sin avisar):** hoy `asegurar_cola_padre()` le pone a la cola padre el mismo límite del plan (por ejemplo, `Plan-3mb` en 3 MB), lo que caparía el total de todos los usuarios de ese plan a 3 MB. El límite de la cola padre debería ser el del internet que suministra el proveedor, y aún no está decidido si habrá una única cola padre para todo el ISP o una por plan con un total asignado. El desplegable solo elige la cola; no cambia esa lógica.

## Autenticación y permisos

Todos los endpoints operativos requieren autenticación (token DRF o sesión; por defecto `IsAuthenticated`). Solicita un token:

```http
POST /api/token/
Content-Type: application/json

{"username": "operador", "password": "clave"}
```

La respuesta es `{"token": "..."}`. Incluye el token recibido:

```http
Authorization: Token EL_TOKEN
```

Roles (ver `api_mikrotik/permissions.py`):

- **Administrador:** acceso completo. También lo son los superusuarios y el personal (`is_staff`).
- **Técnico:** lectura en todo, y edición solo donde está permitido: clientes PPPoE y clientes DHCP/IP fija (`permite_tecnico_edicion = True`). No puede crear ni modificar planes, routers, facturas ni pagos.
- **Solo lectura:** solo peticiones `GET`.

El portal `/api/portal/{token}/` es la única ruta pública actual y devuelve solo `cliente`, `estado`, `servicio` y `mensaje`. No incluya el token del portal en enlaces públicos sin medir exposición. El token del portal no tiene expiración ni rotación automática: eso sigue pendiente.

La API **no pagina**: no hay `DEFAULT_PAGINATION_CLASS` configurado, así que los listados devuelven la lista completa, sin `{"results": [...]}`.

## Catálogo resumido

| Área | Operaciones principales |
|---|---|
| Routers | CRUD, prueba de conexión, estado, sincronización, consumo, leases DHCP, reparación de colas, y listados de direcciones IP, pools y colas simples para los desplegables de planes. |
| Planes | CRUD y sincronización con profile/cola padre. |
| PPPoE | CRUD, sesiones activas, suspensión, ping y desconexión. |
| DHCP/IP fija | CRUD, lease DHCP, ARP fijo, cola y reparación. |
| Facturación | CRUD de facturas y pagos; el estado de la factura se recalcula solo al crear, actualizar o eliminar un pago. |
| Portal | Consulta pública limitada por token privado. |

La descripción completa, parámetros y respuestas están en [Catálogo de la API](docs/api.md) y Swagger. El esquema OpenAPI también está en `api-schema.yaml`: incluye los endpoints `direcciones-ip`, `pools` y `colas`, y los campos `direccion_local` y `pool_remoto` de `PlanVelocidad`.

## Operaciones habituales

```http
POST /api/routers/{id}/verificar-conexion/
POST /api/routers/{id}/sincronizar/
GET  /api/routers/{id}/consumo/
GET  /api/routers/{id}/direcciones-ip/
GET  /api/routers/{id}/pools/
GET  /api/routers/{id}/colas/
POST /api/clientes-pppoe/{id}/ping/
POST /api/clientes-pppoe/{id}/patear/
POST /api/clientes-red/{id}/crear-cola/
```

## Corte programado de facturas

Para suspender clientes con facturas vencidas:

```bash
python manage.py cortar_facturas_vencidas
```

Debes programarlo mediante cron, el Administrador de Tareas de Windows u otro planificador real. La ejecución marca como `vencida` cada factura `pendiente` con `fecha_vencimiento` pasada y, si el cliente no está ya suspendido, lo mueve en RouterOS al perfil `Perfil_Corte` y lo marca `suspendido` en Django.

**Importante:** el perfil `Perfil_Corte` tiene que existir en el router (creado a mano en WinBox). Si no existe, la suspensión en RouterOS falla y el cliente queda como `activo` en Django aunque su factura ya esté `vencida`.

## Pruebas y validación

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test api_mikrotik
python manage.py spectacular --file api-schema.yaml --validate
```

La suite tiene 29 tests. Nota: regenerar el esquema con `spectacular` pierde las descripciones detalladas que tiene el `api-schema.yaml` actual (fueron escritas en el esquema y no están en las anotaciones del código), así que si lo regeneras, revisa el diff antes de guardarlo.

## Documentación técnica

- [Catálogo completo de endpoints](docs/api.md)
- [Arquitectura y modelo operativo](docs/architecture.md)
- [Sincronización bidireccional](docs/synchronization.md)
- [Seguridad: variables de entorno, cifrado de credenciales y API-SSL](docs/security.md)

## Convenciones de desarrollo

- RouterOS debe comunicarse desde los servicios de `api_mikrotik/services/` (`base.py`, `pppoe.py`, `network_clients.py`, `traffic.py`).
- Las vistas de `api_mikrotik/views/` coordinan validación HTTP, persistencia y respuesta.
- No eliminar recursos RouterOS sin confirmar primero que la operación fue exitosa.
- No sincronizar automáticamente sin límites, auditoría y control de conflictos.
- Las credenciales y datos sensibles no deben almacenarse en el código.
- Realizar cambios pequeños, probables de revertir y documentados con commits descriptivos.

## Seguridad antes de producción

Antes de publicar el servicio públicamente:

1. Rota la clave Django (la anterior está en el historial de Git) y define `DJANGO_SECRET_KEY` en el entorno; `DEBUG` ya es `false` por defecto.
2. Limita hosts permitidos, CORS y orígenes aceptados.
3. Usa HTTPS y API-SSL en el router (puerto 8729); las contraseñas de routers y clientes se cifran con `MIKROTIK_CREDENTIALS_KEY` (ver [Seguridad](docs/security.md)).
4. Protege las credenciales RouterOS y PostgreSQL.
5. Activa copias de seguridad y registro de auditoría (la auditoría completa aún no existe: ver [Arquitectura](docs/architecture.md)).
6. Prueba en un entorno aislado y valida cada operación contra el RouterOS real.
7. Añade reintentos, límites de frecuencia y monitoreo.

La funcionalidad existe para operar y desarrollar; todavía no constituye una declaración de preparación comercial completa.

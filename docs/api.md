# Catálogo de la API

La URL base es `http://127.0.0.1:8000/api/`. Swagger está disponible en `/api/docs/` y el esquema OpenAPI en `/api/schema/`.

## Autenticación y permisos

Todos los endpoints operativos requieren autenticación por token o sesión. Obtén un token con:

```http
POST /api/token/
Content-Type: application/json

{"username": "usuario", "password": "clave"}
```

Envía el resultado en las solicitudes posteriores:

```http
Authorization: Token TU_TOKEN
```

`POST /api/token/` devuelve `{"token": "..."}`.

Roles disponibles (ver `api_mikrotik/permissions.py`):

- **Administrador:** acceso completo. También lo son superusuarios y personal (`is_staff`).
- **Técnico/Soporte:** lectura en todo, y edición solo en clientes PPPoE y clientes DHCP/IP fija (`permite_tecnico_edicion = True`). No puede crear ni modificar planes, routers, facturas ni pagos.
- **Solo lectura:** solo peticiones `GET`.

La API **no pagina**: los listados devuelven la lista completa, sin `{"results": [...]}`.

## Routers

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/api/routers/` | Lista routers registrados. |
| `POST` | `/api/routers/` | Registra un router. |
| `GET` | `/api/routers/{id}/` | Consulta un router. |
| `PUT` | `/api/routers/{id}/` | Reemplaza la configuración del router. |
| `PATCH` | `/api/routers/{id}/` | Modifica campos del router. |
| `DELETE` | `/api/routers/{id}/` | Elimina un router sin dependencias protegidas. |
| `POST` | `/api/routers/{id}/verificar-conexion/` | Prueba la API y consulta modelo, versión y uptime. |
| `GET` | `/api/routers/{id}/estado/` | Muestra conexión y registros asociados: `router`, `activo`, `conexion`, `clientes_configurados`, `clientes_red_configurados` y `planes_configurados`. |
| `POST` | `/api/routers/{id}/sincronizar/` | Sincroniza PPPoE y planes de ese router con Django. |
| `GET` | `/api/routers/{id}/consumo/` | Consulta colas simples y contadores: devuelve `router`, `total_colas` y `colas` (cada una con `name`, `parent`, `target`, `max-limit`, `bytes`, `packets`, `rate` y `disabled`). |
| `GET` | `/api/routers/{id}/dhcp-leases/` | Lista leases DHCP dinámicos y estáticos (`router`, `total`, `leases`). |
| `GET` | `/api/routers/{id}/direcciones-ip/` | Lista direcciones IP del router (interfaz + IP) para elegir el local-address del perfil. |
| `GET` | `/api/routers/{id}/pools/` | Lista pools del router (nombre + rangos) para elegir el remote-address del perfil. |
| `GET` | `/api/routers/{id}/colas/` | Lista colas simples del router (nombre, target, max-limit, parent) para elegir la cola padre del plan. |
| `POST` | `/api/routers/{id}/reparar-colas/` | Repara solo las colas simples de los clientes DHCP/IP fija de ese router (no toca sus reservas DHCP/ARP). Devuelve `colas_creadas` y `colas_actualizadas`. |

## Planes

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/api/planes/` | Lista planes locales. |
| `POST` | `/api/planes/` | Crea el plan local, profile PPPoE y cola padre. |
| `GET` | `/api/planes/{id}/` | Consulta un plan. |
| `PUT/PATCH` | `/api/planes/{id}/` | Actualiza el plan y RouterOS. |
| `DELETE` | `/api/planes/{id}/` | Elimina el plan si no tiene clientes asociados. |

Cada plan puede llevar `direccion_local` (IP del loopback de ese router, por
ejemplo `10.1.1.1`) y `pool_remoto` (nombre del pool, por ejemplo
`pool-pppoe`). Son opcionales: si están definidos, la API los envía como
`local-address` y `remote-address` al crear o actualizar el `/ppp/profile`;
si están vacíos, no toca esos campos del perfil que ya existe en el router.
La dirección local es distinta en cada router, por eso se guarda por plan (y
cada plan pertenece a un solo router). Los desplegables se alimentan de
`GET /api/routers/{id}/direcciones-ip/` y `GET /api/routers/{id}/pools/`: el
de direcciones muestra interfaz + IP, pero guarda solo la IP.

La cola padre (`cola_padre`) también es un desplegable, alimentado por
`GET /api/routers/{id}/colas/`, que muestra nombre + max-limit/target de las
colas simples del router y guarda solo el nombre. Es opcional: si se deja
vacía, la API genera una cola padre llamada `Plan-{nombre_perfil}` al crear
el plan.

> **Pendiente de decisión (no cambiar sin avisar):** hoy
> `asegurar_cola_padre()` le pone a la cola padre el mismo límite del plan
> (por ejemplo, `Plan-3mb` en 3 MB). Eso caparía el total de todos los
> usuarios de ese plan a 3 MB, cuando el límite de la cola padre debería ser
> el del internet que suministra el proveedor. Tampoco está decidido si habrá
> una única cola padre para todo el ISP o una por plan con un total asignado.
> El desplegable solo elige la cola; el límite sigue siendo el del plan
> hasta que Adrián decida.

## Clientes PPPoE

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/api/clientes-pppoe/` | Lista clientes PPPoE. Filtros: `estado`, `router`, `plan`; búsqueda por `usuario_pppoe` y `nombre_completo`. |
| `POST` | `/api/clientes-pppoe/` | Crea el cliente y su secreto RouterOS. Si RouterOS falla, el registro local se revierte (la creación va en una transacción). |
| `GET` | `/api/clientes-pppoe/{id}/` | Consulta un cliente. |
| `PUT/PATCH` | `/api/clientes-pppoe/{id}/` | Actualiza localmente y en RouterOS. |
| `DELETE` | `/api/clientes-pppoe/{id}/` | Elimina secreto y registro local. |
| `GET` | `/api/clientes-pppoe/activos/` | Lista conexiones PPP activas. Consulta las sesiones PPP de todos los routers que tienen clientes PPPoE registrados. Devuelve `routers`, `total_conectados`, `conexiones` y `errores`. Si no hay routers con clientes, devuelve 400. |
| `POST` | `/api/clientes-pppoe/{id}/cambiar-estado/` | Activa o suspende el cliente. Recibe `{"estado": "activo"}` o `{"estado": "suspendido"}`; al suspender lo mueve al perfil `Perfil_Corte` en RouterOS. |
| `POST` | `/api/clientes-pppoe/{id}/ping/` | Ejecuta ping desde el router hacia la IP indicada (`{"ip": "..."}`) o la IP de antena guardada. |
| `POST` | `/api/clientes-pppoe/{id}/patear/` | Desconecta las sesiones PPP activas del usuario. |

## Clientes DHCP e IP fija

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/api/clientes-red/` | Lista clientes DHCP/IP fija. Filtros: `estado`, `router`, `plan`, `tipo`; búsqueda por `nombre`, `direccion_ip` y `direccion_mac`. |
| `POST` | `/api/clientes-red/` | Crea cliente, reserva DHCP o ARP estática y cola hijo. La MAC es obligatoria (DHCP: para el lease; IP fija: para la reserva ARP) y debe tener formato `XX:XX:XX:XX:XX:XX`. El plan debe pertenecer al mismo router. |
| `GET` | `/api/clientes-red/{id}/` | Consulta un cliente. |
| `PUT/PATCH` | `/api/clientes-red/{id}/` | Actualiza datos locales, reserva y cola. |
| `DELETE` | `/api/clientes-red/{id}/` | Elimina cola, reserva y registro local. |
| `POST` | `/api/clientes-red/{id}/crear-cola/` | Repara reserva de red y cola simple. |

## Facturación

| Método | Endpoint | Descripción |
|---|---|---|
| `GET/POST` | `/api/facturas/` | Lista o crea facturas mensuales. |
| `GET/PUT/PATCH/DELETE` | `/api/facturas/{id}/` | Gestiona una factura. |
| `GET/POST` | `/api/pagos/` | Lista o registra pagos. |
| `GET/PUT/PATCH/DELETE` | `/api/pagos/{id}/` | Gestiona un pago existente. |

Los pagos creados mediante la API quedan asociados al usuario autenticado en `registrado_por`. El estado de la factura se recalcula automáticamente al crear, actualizar o eliminar un pago: pasa a `pagada` cuando la suma de los pagos alcanza el monto, y vuelve a `pendiente` si queda por debajo (salvo que esté `anulada`, que no cambia).

## Portal público

```http
GET /api/portal/{token}/
```

El token es privado y pertenece al cliente. Esta ruta usa `AllowAny`, pero debe distribuirse solamente por canales controlados. Devuelve solo `cliente`, `estado`, `servicio` y `mensaje`, sin datos operativos ni credenciales. El token del portal no tiene expiración ni rotación automática.

## Comandos administrativos

Los siguientes comandos Django deben ejecutarse manualmente o mediante una tarea programada del sistema:

```bash
python manage.py cifrar_credenciales
python manage.py cortar_facturas_vencidas
```

`cifrar_credenciales` cifra las contraseñas de routers y clientes PPPoE guardadas en texto plano, una sola vez, después de configurar `MIKROTIK_CREDENTIALS_KEY` (ver [Seguridad](security.md)).

`cortar_facturas_vencidas` marca las facturas pendientes vencidas y suspende una vez los clientes PPPoE cuyo pago siga pendiente: cada factura `pendiente` con `fecha_vencimiento` pasada pasa a `vencida`, y el cliente se mueve al perfil `Perfil_Corte` en RouterOS. Ese perfil tiene que existir en el router; si no existe, la suspensión falla y el cliente queda `activo` en Django aunque su factura ya esté `vencida`.

## Convenciones HTTP

- `GET`: consulta sin modificar.
- `POST`: crea o ejecuta una acción.
- `PUT`: reemplaza un recurso completo.
- `PATCH`: modifica campos indicados.
- `DELETE`: elimina un recurso.

Los errores RouterOS se devuelven normalmente como error de integración `502 Bad Gateway` y los datos locales se conservan o se revierten según la operación.

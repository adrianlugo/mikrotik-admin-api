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

`POST /api/token/` devuelve `{"token": "..."}`. Para cerrar sesión y que el
token deje de valer:

```http
POST /api/token/revocar/
Authorization: Token TU_TOKEN
```

Devuelve 200 y elimina el token; después hay que pedir uno nuevo con
`POST /api/token/`. La expiración automática del token es opcional
(`DJANGO_TOKEN_EXPIRY_DAYS`, ver [Seguridad](security.md)).

Roles disponibles (ver `api_mikrotik/permissions.py`):

- **Administrador:** acceso completo. También lo son superusuarios y personal (`is_staff`).
- **Técnico/Soporte:** lectura en todo, y edición solo en clientes PPPoE y clientes DHCP/IP fija (`permite_tecnico_edicion = True`). No puede crear ni modificar planes, routers, facturas ni pagos.
- **Solo lectura:** solo peticiones `GET`.

## Paginación y throttling

Los listados **sí paginan**: devuelven
`{"count": N, "next": "...", "previous": null, "results": [...]}` con 100
elementos por página por defecto. Se puede pedir otra página con
`?page=2` y otro tamaño con `?page_size=50` (máximo 200). La web ya
tolera esta forma: su `get_list()` lee la clave `"results"`. Ojo: la web
solo lee la primera página, así que con más de 100 registros en una lista
la web no vería el resto.

Además hay throttling: 100 peticiones por hora sin autenticar y 1000 por
hora por usuario autenticado (ajustable con `DJANGO_THROTTLE_ANON` y
`DJANGO_THROTTLE_USER`). Si se supera, la API devuelve 429.

## Routers

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/api/routers/` | Lista routers registrados. |
| `POST` | `/api/routers/` | Registra un router. |
| `GET` | `/api/routers/{id}/` | Consulta un router. |
| `PUT` | `/api/routers/{id}/` | Reemplaza la configuración del router. |
| `PATCH` | `/api/routers/{id}/` | Modifica campos del router. |
| `DELETE` | `/api/routers/{id}/` | Elimina un router sin dependencias protegidas. |
| `POST` | `/api/routers/{id}/verificar-conexion/` | Prueba la API y consulta modelo, versión y uptime. Si la conexión falla, devuelve 502 (antes siempre devolvía 200). |
| `GET` | `/api/routers/{id}/estado/` | Muestra conexión y registros asociados: `router`, `activo`, `conexion`, `clientes_configurados`, `clientes_red_configurados` y `planes_configurados`. Si la conexión falla, devuelve 502. |
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
vacía, el plan queda **sin cola padre (none)** y la API no genera ninguna
cola. Si se quiere crear la cola `Plan-{nombre_perfil}`, se pide
explícitamente con `crear_cola_padre=true` al crear o editar el plan
(por ejemplo, `POST /api/planes/ {"router": 1, "nombre_perfil": "3mb",
"subida_mbps": 3, "bajada_mbps": 3, "crear_cola_padre": true}`).

## Cola padre: comportamiento y decisión pendiente

- **Elegir una cola que ya existe no toca su límite.** Antes
  `asegurar_cola_padre()` sobrescribía el `max-limit` de la cola elegida
  con el límite del plan; ahora, si la cola ya existe en el router, se
  deja tal cual está. Así se puede crear la cola a mano en WinBox (por
  ejemplo, la cola con el total que da el proveedor) y solo seleccionarla.
- **Vacío = sin cola padre (none).** El perfil PPPoE se crea sin
  `parent-queue` (en edición se envía `parent-queue=none` para quitar la
  anterior). Al quitar la cola padre de un plan, la cola vieja sigue
  existiendo en el router; no se borra sola.
- **Si se crea una cola nueva, su límite es el del plan.** Solo ocurre en
  dos casos: al pedir explícitamente `crear_cola_padre=true` (se genera
  `Plan-{nombre_perfil}`), o al escribir un nombre de cola que no existe en
  el router. En ambos casos la respuesta avisa: ese límite capa el total
  de los usuarios del plan a la velocidad del plan.

> **Pendiente de decisión (no cambiar sin avisar):** todavía no está
> decidido el total que da el proveedor ni si habrá una única cola padre
> para todo el ISP o una por plan con un total asignado. Por eso la API no
> inventa ningún total: cuando Adrián decida, habrá que poner ese límite a
> la cola padre a mano en WinBox (o elegir la cola del proveedor en el
> desplegable) y, si hace falta, añadir un campo para el total en el plan.

## Clientes PPPoE

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/api/clientes-pppoe/` | Lista clientes PPPoE. Filtros: `estado`, `router`, `plan`; búsqueda por `usuario_pppoe` y `nombre_completo`. |
| `POST` | `/api/clientes-pppoe/` | Crea el cliente y su secreto RouterOS. Si RouterOS falla, el registro local se revierte (la creación va en una transacción). El plan tiene que pertenecer al mismo router que el cliente. |
| `GET` | `/api/clientes-pppoe/{id}/` | Consulta un cliente. |
| `PUT/PATCH` | `/api/clientes-pppoe/{id}/` | Actualiza localmente y en RouterOS. |
| `DELETE` | `/api/clientes-pppoe/{id}/` | Elimina secreto y registro local. |
| `GET` | `/api/clientes-pppoe/activos/` | Lista conexiones PPP activas. Consulta las sesiones PPP de todos los routers que tienen clientes PPPoE registrados. Devuelve `routers`, `total_conectados`, `conexiones` y `errores`. Si no hay routers con clientes, devuelve 400. Si ningún router responde, devuelve 502 (antes devolvía 200 con 0 conectados). Si solo falla alguno, devuelve 200 con los que respondieron y el fallo en `errores`. |
| `POST` | `/api/clientes-pppoe/{id}/cambiar-estado/` | Activa o suspende el cliente. Recibe `{"estado": "activo"}` o `{"estado": "suspendido"}`; al suspender lo mueve al perfil `Perfil_Corte` en RouterOS. Si ese perfil no existe en el router, devuelve error y el cliente sigue activo (no cambia nada). |
| `POST` | `/api/clientes-pppoe/{id}/ping/` | Ejecuta ping desde el router hacia la IP indicada (`{"ip": "..."}`) o la IP de antena guardada. Si el ping no se ejecuta, devuelve error (502), nunca un éxito inventado. |
| `POST` | `/api/clientes-pppoe/{id}/patear/` | Desconecta las sesiones PPP activas del usuario. |
| `POST` | `/api/clientes-pppoe/{id}/rotar-portal-token/` | Genera un `portal_token` nuevo para el cliente (solo administradores) e invalida el anterior. El token nuevo se devuelve una sola vez en la respuesta. |

## Clientes DHCP e IP fija

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/api/clientes-red/` | Lista clientes DHCP/IP fija. Filtros: `estado`, `router`, `plan`, `tipo`; búsqueda por `nombre`, `direccion_ip` y `direccion_mac`. |
| `POST` | `/api/clientes-red/` | Crea cliente, reserva DHCP o ARP estática y cola hijo. La MAC es obligatoria (DHCP: para el lease; IP fija: para la reserva ARP) y debe tener formato `XX:XX:XX:XX:XX:XX`. El plan debe pertenecer al mismo router. |
| `GET` | `/api/clientes-red/{id}/` | Consulta un cliente. |
| `PUT/PATCH` | `/api/clientes-red/{id}/` | Actualiza datos locales, reserva y cola. Es atómico: si la reserva o la cola fallan en el router, los cambios locales se revierten y la API devuelve 502. |
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

El token es privado y pertenece al cliente. Esta ruta usa `AllowAny`, pero debe distribuirse solamente por canales controlados. Devuelve solo `cliente`, `estado`, `servicio` y `mensaje`, sin datos operativos ni credenciales. El token del portal no caduca solo: se rota a mano con `POST /api/clientes-pppoe/{id}/rotar-portal-token/` (solo administradores), que invalida el enlace anterior.

## Comandos administrativos

Los siguientes comandos Django deben ejecutarse manualmente o mediante una tarea programada del sistema:

```bash
python manage.py cifrar_credenciales
python manage.py cortar_facturas_vencidas
python manage.py respaldar_bd
```

`cifrar_credenciales` cifra las contraseñas de routers y clientes PPPoE guardadas en texto plano, una sola vez, después de configurar `MIKROTIK_CREDENTIALS_KEY` (ver [Seguridad](security.md)).

`cortar_facturas_vencidas` suspende los clientes PPPoE con facturas pendientes vencidas y después marca esas facturas como vencidas. El orden importa: primero se suspende en el router y solo si eso funciona se marca la factura. Si la suspensión falla, la factura **no** se marca y queda pendiente para el próximo intento, y el comando avisa del fallo al final. Antes de suspender comprueba que exista el perfil `Perfil_Corte` en el router:

- Si no existe, no marca nada y avisa. Para crearlo, hazlo en WinBox (`/ppp/profile`, con velocidad casi nula) o ejecuta el comando con la opción `--crear-perfil-corte`, que lo crea con `rate-limit 1k/1k`.
- Si el cliente ya estaba suspendido, la factura se marca directamente sin tocar el router.

Para programarlo todos los días y para el respaldo, ver [Despliegue](deployment.md).

`respaldar_bd` copia `db.sqlite3` a `backups/` con fecha y hora y conserva las 7 últimas copias (`--destino` y `--conservar` cambian la carpeta y la cantidad). Solo sirve para SQLite; con PostgreSQL el respaldo es con `pg_dump`.

## Convenciones HTTP

- `GET`: consulta sin modificar.
- `POST`: crea o ejecuta una acción.
- `PUT`: reemplaza un recurso completo.
- `PATCH`: modifica campos indicados.
- `DELETE`: elimina un recurso.

Los errores RouterOS se devuelven normalmente como error de integración `502 Bad Gateway` y los datos locales se conservan o se revierten según la operación. Los endpoints de lectura que consultan el router (`activos`, `consumo`, `dhcp-leases`, `direcciones-ip`, `pools`, `colas`, `verificar-conexion`, `estado`) devuelven 502 cuando el router no responde, en vez de un 200 con listas vacías o con 0. El ping devuelve error si no se ejecuta.

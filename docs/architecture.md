# Arquitectura y evolución del proyecto

## Objetivo

La API administra clientes ISP y sincroniza la configuración necesaria con routers MikroTik. El proyecto está separado por responsabilidades para permitir crecimiento sin duplicar la lógica RouterOS en las vistas.

## Capas actuales

```text
Cliente HTTP / Swagger
        |
api_mikrotik/views/       (auth_views, billing_views, network_views,
                           pppoe_views, router_views)
        |
serializers.py -> validación de entrada
        |
models.py -> persistencia Django
        |
api_mikrotik/services/    (base.py, pppoe.py, network_clients.py,
                           traffic.py) -> comunicación con RouterOS
        |
MikroTik
```

## Responsabilidades

### `models.py`

Contiene los datos que deben persistir localmente:

- Router.
- Plan de velocidad (`PlanVelocidad`: router, `nombre_perfil`, `cola_padre`, `subida_mbps`, `bajada_mbps`, `direccion_local`, `pool_remoto`).
- Cliente PPPoE.
- Cliente DHCP/IP fija.
- Perfil operativo y rol de usuario (`PerfilUsuario`: `administrador`, `tecnico`, `lectura`; se crea solo al crear el usuario, superusuario → `administrador`, resto → `lectura`).
- Factura y pago.

Los datos locales deben representar lo que el ISP desea configurar. Las IDs y estadísticas temporales de RouterOS no deben reemplazar este modelo de negocio.

### `serializers.py`

Valida datos recibidos por la API. Debe evitar:

- Asociar un plan de un router a un cliente de otro router.
- Direcciones MAC inválidas (formato `XX:XX:XX:XX:XX:XX`; obligatoria para DHCP e IP fija).
- Usuarios PPPoE incompatibles con RouterOS (minúsculas, `^[a-z0-9._-]+$`).
- Contraseñas cortas (mínimo 6 caracteres) o campos inconsistentes.
- Activar un cliente en un router marcado como fuera de servicio (`activo = false`).

### `views/`

Expone operaciones HTTP y coordina transacciones. Las vistas deben contener poco trabajo con RouterOS; las llamadas reales deben permanecer en `services/`. Los permisos por rol están en `permissions.py` (`PermisoOperativo`): el Técnico solo edita clientes PPPoE y clientes DHCP/IP fija; planes, routers, facturas y pagos son solo de Administrador.

### `services/`

Centraliza los recursos RouterOS, por dominio:

- `pppoe.py` (`PPPoEService`): `/ppp/profile`, `/ppp/secret`, `/ppp/active`, `/ip/address`, `/ip/pool`, sincronización.
- `network_clients.py` (`NetworkClientService`): `/ip/dhcp-server/lease`, `/ip/arp`, colas hijo de clientes de red.
- `traffic.py` (`TrafficService`): `/queue/simple` (listado, cola padre, consumo).
- `base.py` (`MikroTikBaseService`): conexión API-SSL, verificación (`/system/resource`), ping.

No debe contener reglas de negocio de Django salvo los registros necesarios para importar o sincronizar datos.

El modo simulación (`MIKROTIK_SIMULATION_MODE`) está fijado a `false` en `core/settings.py` y no tiene variable de entorno: los servicios hablan con el router real.

## Modelo operativo recomendado

La configuración base de la red debe hacerse una vez en WinBox y cambiarse poco:

```text
WAN, NAT, bridge LAN, servidor PPPoE, servidor DHCP, firewall y cola padre global
```

La API administrará únicamente elementos dinámicos y reversibles:

```text
/ppp/secret             -> cuentas PPPoE
/ip/dhcp-server/lease   -> leases estáticos DHCP
/ip/arp                 -> asociaciones IP/MAC de IP fija
/queue/simple           -> colas hijo de DHCP/IP fija
```

Esta separación evita exponer a operadores la configuración crítica del router. Los elementos fijos pueden respaldarse y recuperarse independientemente de los clientes gestionados por Django.

Cada plan representa el perfil PPPoE y una cola padre RouterOS. Los clientes PPPoE no necesitan una cola simple adicional; DHCP e IP fija sí requieren cola hijo vinculada al padre de su plan.

## Recursos administrados

### PPPoE

RouterOS usa profiles y secrets. El profile contiene el límite y la cola padre posible; el secret contiene usuario, contraseña, profile y estado operativo.

### DHCP/IP fija

Estos clientes se representan mediante una dirección IP, MAC opcional, plan y tipo. RouterOS necesita una cola simple hijo asociada al `cola_padre` del plan.

### Colas

La jerarquía visual propuesta es:

```text
Internet global
└── Cola padre del plan
    ├── Cola hijo PPPoE, cuando haya colas dinámicas simples
    ├── Cola hijo DHCP
    └── Cola hijo IP fija
```

Una cola padre representa el límite agregado de un plan. Una cola hija representa el consumo y límites individuales.

> **Pendiente de decisión:** hoy `asegurar_cola_padre()` le pone a la cola padre el mismo límite del plan, lo que caparía el total de todos los usuarios de ese plan a ese límite. El límite de la cola padre debería ser el del internet que suministra el proveedor, y aún no está decidido si habrá una única cola padre para todo el ISP o una por plan con un total asignado.

## Sincronización

La sincronización oficial es manual y usa el router seleccionado por ID:

```http
POST /api/routers/{id}/sincronizar/
```

Antes de automatizarla se recomienda guardar diferencias y añadir aprobación. La reconciliación automática debe limitarse inicialmente a recursos reparables, sin eliminar datos desconocidos.

## Monitoreo y consumo histórico

Las estadísticas devueltas por `/queue/simple` son valores de trabajo en vivo (`GET /api/routers/{id}/consumo/`). Django **no** almacena snapshots históricos: no existe un modelo `ConsumoCola`. El modelo siguiente es solo una propuesta, no código existente:

```text
ConsumoCola
- router
- cola
- cliente opcional
- bytes recibidos
- bytes enviados
- paquetes
- velocidad registrada
- fecha/hora
```

## Estado de evolución

Ya implementado:

1. CRUD DHCP/IP fija y reservas RouterOS.
2. Autenticación por token y roles operativos.
3. Facturación, pagos y corte de facturas vencidas.
4. Diagnóstico por ping y desconexión PPPoE.
5. Portal limitado por token.
6. Sincronización manual por router específico.
7. Cifrado Fernet de contraseñas de routers y clientes PPPoE en reposo.
8. Servicios RouterOS separados por dominio (`services/pppoe.py`, `network_clients.py`, `traffic.py`, `base.py`).
9. Campos `direccion_local` y `pool_remoto` en el plan, con desplegables de direcciones, pools y colas por router.

Pendiente para consolidar:

1. Añadir inventario visual de diferencias antes de sincronizar.
2. Guardar consumo histórico en intervalos periódicos (hoy el consumo es solo en vivo).
3. Programar y supervisar tareas automáticas.
4. Añadir auditoría completa de cambios manuales y automáticos.
5. Implementar métricas, alertas y panel web separado.
6. Rotación y expiración de tokens (DRF y portal) y paginación/throttling.
7. Decidir el límite de la cola padre (ver arriba).

## Límites del modelo comercial futuro

Un ISP real debe incorporar, antes de producción comercial:

- Transacciones de facturación.
- Suspensiones por vencimiento (el perfil `Perfil_Corte` debe existir en el router).
- Auditoría de todas las operaciones.
- Cifrado de credenciales (ya implementado: ver [Seguridad](security.md)).
- Permisos por rol.
- Conflictos de sincronización visibles.
- Reintentos de API y manejo de desconexiones.
- Respaldos y recuperación ante desastres.
- Tests con simulador de RouterOS y pruebas de integración controladas (la suite actual usa mocks, no un simulador).

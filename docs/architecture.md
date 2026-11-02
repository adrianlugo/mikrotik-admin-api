# Arquitectura y evolución del proyecto

## Objetivo

La API administra clientes ISP y sincroniza la configuración necesaria con routers MikroTik. El proyecto está separado por responsabilidades para permitir crecimiento sin duplicar la lógica RouterOS en las vistas.

## Capas actuales

```text
Cliente HTTP / Swagger
        |
api_mikrotik/views.py
        |
serializers.py -> validación de entrada
        |
models.py -> persistencia Django
        |
services.py -> comunicación con RouterOS
        |
MikroTik
```

## Responsabilidades

### `models.py`

Contiene los datos que deben persistir localmente:

- Router.
- Plan de velocidad.
- Cliente PPPoE.
- Cliente DHCP/IP fija.
- Perfil operativo y rol de usuario.
- Factura y pago.

Los datos locales deben representar lo que el ISP desea configurar. Las IDs y estadísticas temporales de RouterOS no deben reemplazar este modelo de negocio.

### `serializers.py`

Valida datos recibidos por la API. Debe evitar:

- Asociar un plan de un router a un cliente de otro router.
- Direcciones MAC inválidas.
- Usuarios PPPoE incompatibles con RouterOS.
- Contraseñas cortas o campos inconsistentes.

### `views.py`

Expone operaciones HTTP y coordina transacciones. Las vistas deben contener poco trabajo con RouterOS; las llamadas reales deben permanecer en `services.py`.

### `services.py`

Centraliza los recursos RouterOS:

- `/ppp/profile`.
- `/ppp/secret`.
- `/queue/simple`.
- `/ip/dhcp-server/lease`.
- `/ppp/active`.
- `/system/resource`.

No debe contener reglas de negocio de Django salvo los registros necesarios para importar o sincronizar datos.

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

## Sincronización

La sincronización oficial es manual y usa el router seleccionado por ID:

```http
POST /api/routers/{id}/sincronizar/
```

Antes de automatizarla se recomienda guardar diferencias y añadir aprobación. La reconciliación automática debe limitarse inicialmente a recursos reparables, sin eliminar datos desconocidos.

## Monitoreo y consumo histórico

Las estadísticas devueltas por `/queue/simple` son valores de trabajo. Django debe almacenar snapshots históricos si el sistema necesita:

- Consumo diario.
- Consumo mensual.
- Velocidad actual.
- Anomalías y alertas.

Modelo sugerido:

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

Pendiente para consolidar:

1. Añadir inventario visual de diferencias antes de sincronizar.
2. Guardar consumo histórico en intervalos periódicos.
3. Programar y supervisar tareas automáticas.
4. Proteger credenciales mediante cifrado o un almacén de secretos.
5. Añadir auditoría completa de cambios manuales y automáticos.
6. Implementar métricas, alertas y panel web separado.
7. Separar servicios RouterOS por dominios cuando crezca el proyecto: PPPoE, IP, colas, firewall y sistema.

## Límites del modelo comercial futuro

Un ISP real debe incorporar, antes de producción comercial:

- Transacciones de facturación.
- Suspensiones por vencimiento.
- Auditoría de todas las operaciones.
- Cifrado de credenciales.
- Permisos por rol.
- Conflictos de sincronización visibles.
- Reintentos de API y manejo de desconexiones.
- Respaldos y recuperación ante desastres.
- Tests con simulador de RouterOS y pruebas de integración controladas.

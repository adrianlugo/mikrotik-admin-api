# MikroTik Admin API

API basada en Django REST Framework para administrar el acceso a Internet, routers MikroTik y la operación diaria de un ISP.

## Estado del proyecto

El proyecto incluye gestión operativa para PPPoE, DHCP, IP fija, planes de velocidad, colas, facturación, diagnósticos RouterOS, autenticación y sincronización manual por router. Todavía requiere validaciones en hardware real, endurecimiento de producción y automatización del portal y el monitoreo antes de considerarse comercial.

## Capacidades principales

- Registro y conexión a uno o varios routers MikroTik.
- CRUD de planes y perfiles PPPoE.
- Alta, modificación, suspensión y eliminación de clientes PPPoE.
- Gestión de clientes DHCP con lease estático.
- Gestión de clientes con IP fija mediante entrada ARP estática.
- Creación y reparación de colas simples hijo relacionadas con una cola padre del plan.
- Consulta de sesiones activas, leases, colas y consumo disponible.
- Sincronización bidireccional manual seleccionando el router por ID.
- Ping y desconexión de clientes PPPoE desde RouterOS.
- Autenticación por token/sesión y roles Administrador, Técnico y Solo lectura.
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
/queue/simple           -> colas hijo de DHCP/IP fija
/ppp/profile            -> perfiles y límites PPPoE
```

PPPoe usa profiles para aplicar el plan; DHCP e IP fija usan una cola simple hija cuando se administra desde Django. Consulte [Arquitectura](docs/architecture.md) para las responsabilidades técnicas.

## Requisitos

- Windows o entorno compatible con Python.
- Python 3.13 o compatible.
- Dependencias indicadas en `requirements.txt`.
- PostgreSQL, SQLite u otro motor compatible configurado en Django.
- API RouterOS habilitada y credenciales dedicadas.
- API-SSL habilitado en el router (puerto 8729) con un certificado válido; el puerto 8728 sin cifrar está bloqueado por defecto (ver [Seguridad](docs/security.md)).

## Instalación de desarrollo

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cp .env.example .env
# Edita .env: define DJANGO_SECRET_KEY y MIKROTIK_CREDENTIALS_KEY
# (genera los valores con los comandos indicados en .env.example).
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Si ya tenías routers y clientes guardados con contraseñas en texto plano,
cifra las credenciales existentes después de configurar la clave:

```powershell
python manage.py cifrar_credenciales
```

Ver [Seguridad](docs/security.md) para la rotación de la `SECRET_KEY`, el
cifrado de credenciales y la configuración de API-SSL en el router.

Después abre:

- API: `http://127.0.0.1:8000/api/`
- Swagger: `http://127.0.0.1:8000/api/docs/`
- ReDoc: `http://127.0.0.1:8000/api/redoc/`
- Esquema YAML: `http://127.0.0.1:8000/api/schema/`
- Administración: `http://127.0.0.1:8000/admin/`

## Flujo inicial

1. Configura la red base en WinBox.
2. Inicia sesión o crea un usuario con rol Administrador.
3. Registra el router en `/api/routers/` o `/admin/`.
4. Ejecuta `/api/routers/{id}/verificar-conexion/`.
5. Crea un plan con velocidades y cola padre.
6. Da de alta clientes PPPoE, DHCP o IP fija.
7. Usa la sincronización manual del router para reconciliar recursos existentes.
8. Consulta activos, leases, colas y consumo desde los endpoints de monitoreo.

## Autenticación

Todos los endpoints operativos requieren autenticación. Solicita un token:

```http
POST /api/token/
Content-Type: application/json

{"username": "operador", "password": "clave"}
```

Incluye el token recibido:

```http
Authorization: Token EL_TOKEN
```

El portal `/api/portal/{token}/` es la única ruta pública actual y devuelve datos limitados. No incluya el token del portal en enlaces públicos sin medir exposición.

## Catálogo resumido

| Área | Operaciones principales |
|---|---|
| Routers | CRUD, prueba de conexión, estado, sincronización, consumo y leases DHCP. |
| Planes | CRUD y sincronización con profile/cola padre. |
| PPPoE | CRUD, sesión activa, suspensión, ping y desconexión. |
| DHCP/IP fija | CRUD, lease DHCP, ARP fijo, cola y reparación. |
| Facturación | CRUD de facturas y pagos. |
| Portal | Consulta pública limitada por token privado. |

La descripción completa, parámetros y respuestas están en [Catálogo de la API](docs/api.md) y Swagger.

## Operaciones habituales

```http
POST /api/routers/{id}/verificar-conexion/
POST /api/routers/{id}/sincronizar/
GET  /api/routers/{id}/consumo/
POST /api/clientes-pppoe/{id}/ping/
POST /api/clientes-pppoe/{id}/patear/
POST /api/clientes-red/{id}/crear-cola/
```

## Corte programado de facturas

Para suspender clientes con facturas vencidas:

```powershell
python manage.py cortar_facturas_vencidas
```

Debes programarlo mediante el Administrador de Tareas de Windows, cron u otro planificador real. La ejecución marca facturas vencidas y cambia al perfil PPPoE `Perfil_Corte`.

## Pruebas y validación

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test api_mikrotik
python manage.py spectacular --file api-schema.yaml --validate
```

## Documentación técnica

- [Catálogo completo de endpoints](docs/api.md)
- [Arquitectura y modelo operativo](docs/architecture.md)
- [Sincronización bidireccional](docs/synchronization.md)
- [Seguridad: variables de entorno, cifrado de credenciales y API-SSL](docs/security.md)

## Convenciones de desarrollo

- RouterOS debe comunicarse desde `MikroTikService`.
- Las vistas coordinan validación HTTP, persistencia y respuesta.
- No eliminar recursos RouterOS sin confirmar primero que la operación fue exitosa.
- No sincronizar automáticamente sin límites, auditoría y control de conflictos.
- Las credenciales y datos sensibles no deben almacenarse en el código.
- Realizar cambios pequeños, probables de revertir y documentados con commits descriptivos.

## Seguridad antes de producción

Antes de publicar el servicio públicamente:

1. Rota la clave Django (la anterior está en el historial de Git) y define `DJANGO_SECRET_KEY` en el entorno; `DEBUG` ya es `false` por defecto.
2. Limita hosts permitidos, CORS y origenes aceptados.
3. Usa HTTPS y API-SSL en el router (puerto 8729); las contraseñas de routers y clientes se cifran con `MIKROTIK_CREDENTIALS_KEY` (ver [Seguridad](docs/security.md)).
4. Protege las credenciales RouterOS y PostgreSQL.
5. Activa copias de seguridad y registro de auditoría.
6. Prueba en un entorno aislado y valida cada operación contra el RouterOS real.
7. Añade reintentos, límites de frecuencia y monitoreo.

La funcionalidad existe para operar y desarrollar; todavía no constituye una declaración de preparación comercial completa.

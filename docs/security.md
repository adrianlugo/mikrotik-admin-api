# Seguridad

Este documento describe cómo están protegidas las credenciales en
`mikrotik-admin-api` y qué pasos manuales hay que hacer al desplegar.

## Qué se cifra y qué no

| Dato | Protección |
| --- | --- |
| `Router.password` y `ClientePPPoE.password_pppoe` | Cifrado simétrico Fernet en la base de datos cuando `MIKROTIK_CREDENTIALS_KEY` está configurada. Sin la clave, se guardan en texto plano (compatibilidad con datos existentes) y se registra una advertencia. |
| Contraseñas en las respuestas de la API | Nunca se devuelven: los serializers las marcan `write_only` y `portal_token` no se incluye en las respuestas. |
| Conexión con el router | API-SSL (TLS, puerto 8729) con verificación de certificado por defecto. |
| `SECRET_KEY` de Django | Variable de entorno `DJANGO_SECRET_KEY`. Nunca en el código. |

## Variables de entorno

Ver `.env.example`. Las importantes para seguridad son:

- `DJANGO_SECRET_KEY`: obligatoria en producción. Generarla con:
  `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`.
- `DJANGO_DEBUG`: `false` en producción (es el valor por defecto).
- `DJANGO_ALLOWED_HOSTS`: dominios separados por comas.
- `MIKROTIK_CREDENTIALS_KEY`: clave Fernet para cifrar credenciales. Generarla con:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- `MIKROTIK_SSL_VERIFY` / `MIKROTIK_SSL_VERIFY_HOSTNAME`: `true` por defecto.
  Ponerlas en `false` solo con certificados autofirmados en laboratorio.
- `MIKROTIK_ALLOW_INSECURE_API`: `false` por defecto. Solo laboratorio.
- `DJANGO_TOKEN_EXPIRY_DAYS`: días que dura el token DRF (`0` = no caduca,
  que es el valor por defecto). Ejemplo: `30`.
- `DJANGO_HTTPS_EXTERNO`: `false` por defecto. Solo se pone en `true`
  cuando la API se expone fuera de la PC con HTTPS (ver «HTTPS y cabeceras
  seguras» más abajo). En local debe seguir en `false`.
- `DJANGO_DETRAS_DE_PROXY`: `true` solo si hay un proxy inverso (nginx)
  delante y `DJANGO_HTTPS_EXTERNO=true`.

## Tokens: revocación, rotación y expiración

- **Revocar el token DRF (cerrar sesión):** `POST /api/token/revocar/`
  con el token en `Authorization`. Elimina el token y cierra la sesión;
  después hay que pedir uno nuevo con `POST /api/token/`. Antes no había
  forma de cerrar sesión: el token seguía valiendo aunque se cerrara la
  sesión en la web.
- **Expiración opcional:** con `DJANGO_TOKEN_EXPIRY_DAYS=30`, los tokens
  con más de 30 días dejan de valer (se eliminan y la API responde 401).
  Por defecto está desactivada (0) para no romper el uso actual: la web
  guarda el token en sesión y Adrián lo usa en local. Si se activa, todos
  los operadores tendrán que pedir un token nuevo cuando caduque el suyo.
- **Rotar el token del portal:** `POST
  /api/clientes-pppoe/{id}/rotar-portal-token/` (solo administradores).
  Genera un `portal_token` nuevo e invalida el anterior: el enlace viejo
  del portal deja de funcionar. El token nuevo se devuelve una sola vez
  en la respuesta. El portal no tiene expiración automática: si un enlace
  se filtra, se rota a mano con este endpoint.

## HTTPS y cabeceras seguras (solo para el servidor, no para local)

En local la API escucha en 127.0.0.1 y `DJANGO_HTTPS_EXTERNO` debe seguir
en `false`. Cuando la API se monte en un servidor con dominio y HTTPS, se
pone `DJANGO_HTTPS_EXTERNO=true` en el `.env` y Django activa: redirección
a HTTPS, cookies de sesión y CSRF seguras, HSTS (1 año) y cabeceras
`X-Content-Type-Options`, `X-XSS-Protection` y `X-Frame-Options: DENY`.
Con nginx delante, además `DJANGO_DETRAS_DE_PROXY=true` para que Django
confíe en `X-Forwarded-Proto`.

## Rotar la SECRET_KEY (obligatorio)

La clave anterior estaba escrita en `core/settings.py` y por tanto en el
historial de Git: hay que considerarla expuesta y rotarla. Al cambiar
`DJANGO_SECRET_KEY` se invalidan todas las sesiones y tokens de Django
existentes; los usuarios tendrán que volver a iniciar sesión y pedir un
token nuevo con `POST /api/token/`.

## Credenciales ya guardadas en texto plano

La migración `0005` solo alarga los campos; no cifra los valores existentes.
Después de configurar `MIKROTIK_CREDENTIALS_KEY`, cifra las credenciales
existentes con:

```powershell
python manage.py cifrar_credenciales
```

O reintroduce cada contraseña desde la API o el admin (al guardarla se
cifra automáticamente). **Guarda la clave de cifrado fuera del repositorio.**
Si se pierde o se cambia, las credenciales cifradas no se pueden descifrar
y habrá que reintroducirlas todas.

## Conexión segura con el router (API-SSL)

La API se conecta por defecto al puerto **8729** con TLS y
`plaintext_login=True`. Ese parámetro es obligatorio en RouterOS >= 6.43,
pero la contraseña no viaja en texto plano por la red: va dentro de la
sesión TLS. Las conexiones sin SSL (puerto 8728) se rechazan salvo que se
active explícitamente `MIKROTIK_ALLOW_INSECURE_API=true` (solo laboratorio).

En el router hay que habilitar el servicio api-ssl con un certificado.
Ejemplo en terminal de RouterOS (adapta el nombre del certificado):

```routeros
/certificate
# Crea o importa un certificado para el router, por ejemplo con Let's Encrypt
# o uno autofirmado, y asígnalo al servicio:
/ip service set api-ssl disabled=no port=8729 certificate=<nombre-del-certificado>
# Cierra el servicio API sin cifrar:
/ip service set api disabled=yes
```

Después cambia el `puerto_api` de cada router registrado a `8729` (es el
valor por defecto para los routers nuevos). Los routers ya registrados
conservan el puerto que tenían guardado: hay que actualizarlo a 8729 en la
API (`PATCH /api/routers/{id}/`) o en el admin.

## Qué queda pendiente (no cubierto por este cambio)

- Rotación de la `SECRET_KEY` (arriba) y de las credenciales de los routers
  si alguna vez estuvieron expuestas.
- El esquema OpenAPI (`api-schema.yaml`) incluye los endpoints
  `direcciones-ip`, `pools`, `colas` y `token/revocar`, el campo
  `direccion_local`, `pool_remoto` y `crear_cola_padre` en planes. Ojo al
  regenerarlo con `python manage.py spectacular --file api-schema.yaml
  --validate`: la regeneración pierde las descripciones detalladas del
  esquema actual, que no están en las anotaciones del código; revisa el
  diff antes de guardarlo. Por ese motivo, en el cambio de preparación
  para producción (2026-11-26) el esquema se actualizó a mano (respuestas
  paginadas, parámetros `page`/`page_size` y los endpoints nuevos), sin
  regenerarlo entero.

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
- Expiración/rotación del token del portal y del token de autenticación de
  DRF, y paginación/throttling: están fuera del alcance de este arreglo y
  siguen pendientes según la revisión del 2026-11-25.
- Regenerar el esquema OpenAPI tras cambiar los serializers:
  `python manage.py spectacular --file api-schema.yaml --validate`.

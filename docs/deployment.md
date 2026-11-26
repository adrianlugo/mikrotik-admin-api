# Despliegue y operación

## Cómo se usa hoy: en local en la PC

Adrián todavía no tiene un servidor de producción: la API y la web corren
en local en su PC. **Eso está bien y no cambia con este cambio.** En local
se sigue usando el servidor de desarrollo de Django:

```powershell
python manage.py runserver
```

`runserver` es solo para desarrollo y uso local (127.0.0.1): no sirve para
exponer la API a internet ni para atender muchos usuarios a la vez. Mientras
la API solo la usen Adrián y la web desde su PC, es suficiente.

Lo que sí conviene hacer ya en local (todo con comandos sencillos):

1. **Respaldo de la base de datos** (SQLite, un solo archivo `db.sqlite3`):

   ```powershell
   python manage.py respaldar_bd
   ```

   Guarda una copia con fecha y hora en `backups/` y conserva las 7
   últimas. Para guardar las copias en otra carpeta (por ejemplo un disco
   externo o una carpeta sincronizada):

   ```powershell
   python manage.py respaldar_bd --destino D:\respaldos --conservar 14
   ```

   Si la base fuera PostgreSQL, este comando no sirve: ahí el respaldo es
   con `pg_dump` (ver «PostgreSQL (opcional)» más abajo).

2. **Corte de facturas vencidas, programado**: el comando
   `cortar_facturas_vencidas` hay que ejecutarlo todos los días (por
   ejemplo, de madrugada). En Windows se programa con el Programador de
   tareas. Con `schtasks` desde una terminal con permisos de administrador
   (adapta las rutas a tu PC):

   ```powershell
   schtasks /create /tn "MikroTik corte facturas" /tr "C:\ruta\a\mikrotik-admin-api\venv\Scripts\python.exe C:\ruta\a\mikrotik-admin-api\manage.py cortar_facturas_vencidas" /sc daily /st 02:00
   schtasks /create /tn "MikroTik respaldo BD" /tr "C:\ruta\a\mikrotik-admin-api\venv\Scripts\python.exe C:\ruta\a\mikrotik-admin-api\manage.py respaldar_bd" /sc daily /st 03:00
   ```

   O desde la interfaz gráfica: Programador de tareas → Crear tarea básica
   → Desencadenador diario → Acción «Iniciar un programa» con esos mismos
   comandos. El corte escribe en la salida cuántas facturas marcó, cuántos
   clientes suspendió y cuántos fallos hubo; si el perfil `Perfil_Corte`
   no existe en el router, no marca nada y avisa (ver
   [Catálogo de la API](api.md#comandos-administrativos)).

3. **Logs**: la API escribe en `logs/mikrotik-admin-api.log` (además de la
   consola). Ahí quedan los errores de conexión con los routers. La ruta
   se puede cambiar con `DJANGO_LOG_FILE` en el `.env`.

## Producción (opcional, para más adelante)

Cuando Adrián monte un servidor (una PC o VPS con Linux), estos son los
pasos. **Nada de esto es obligatorio hoy ni hay que instalarlo en la PC.**

### 1. Servidor de aplicación: gunicorn (no runserver)

`gunicorn` ya está en `requirements.txt`. En el servidor:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn core.wsgi:application --bind 127.0.0.1:8000 --workers 2 --timeout 60
```

`STATIC_ROOT` ya está configurado (`staticfiles/`); `collectstatic` reúne
ahí los archivos estáticos para servirlos con nginx o con el propio
servidor. Detrás de gunicorn conviene poner nginx como proxy inverso con
HTTPS (certificado Let's Encrypt) y servir los estáticos desde
`staticfiles/`.

Para que el servicio arranque solo con el servidor, hay un ejemplo de
unidad systemd en `deploy/mikrotik-admin-api.service` (hay que adaptar
rutas y usuario). También hay un `deploy/Dockerfile` de ejemplo para
correrlo en Docker, con la base SQLite en un volumen para que no se pierda
al recrear el contenedor.

### 2. HTTPS y cabeceras seguras

En local `DJANGO_HTTPS_EXTERNO` debe seguir en `false`. En el servidor,
con dominio y HTTPS, se pone en `true` en el `.env`: activa redirección a
HTTPS, cookies seguras, HSTS y cabeceras de seguridad. Si hay un proxy
inverso (nginx) delante, además `DJANGO_DETRAS_DE_PROXY=true`. Ver
[Seguridad](security.md).

### 3. PostgreSQL (opcional)

La base por defecto sigue siendo **SQLite** (`db.sqlite3`): no se cambió,
porque en local es lo más sencillo y basta para un ISP pequeño. Si el
servidor crece (varios operadores a la vez, más clientes), se puede pasar
a PostgreSQL con las variables del `.env.example`:

```text
DJANGO_DATABASE_ENGINE=django.db.backends.postgresql
DJANGO_DATABASE_NAME=mikrotik_admin
DJANGO_DATABASE_USER=...
DJANGO_DATABASE_PASSWORD=...
DJANGO_DATABASE_HOST=127.0.0.1
DJANGO_DATABASE_PORT=5432
```

Para migrar los datos de SQLite a PostgreSQL hay que volcar y cargar los
datos (`dumpdata`/`loaddata`) y probar en un entorno aparte antes de
cambiar. Con PostgreSQL el respaldo ya no es copiar un archivo: es
`pg_dump mikrotik_admin > respaldo.sql`, y el comando `respaldar_bd`
avisa de que no sirve para ese motor.

### 4. Corte programado en Linux

En el servidor Linux el corte se programa con cron (o con un timer de
systemd). Ejemplo de cron diario a las 02:00:

```cron
0 2 * * * cd /opt/mikrotik-admin-api && /opt/mikrotik-admin-api/venv/bin/python manage.py cortar_facturas_vencidas >> /var/log/mikrotik-corte.log 2>&1
0 3 * * * cd /opt/mikrotik-admin-api && /opt/mikrotik-admin-api/venv/bin/python manage.py respaldar_bd >> /var/log/mikrotik-respaldo.log 2>&1
```

## Qué sigue pendiente

- **Decisión de Adrián**: el total que le da su proveedor y si habrá una
  cola padre global o una por plan (ver [Catálogo](api.md)).
- **Probar contra hardware real**: hasta hoy todo se validó con mocks,
  nunca contra un router real con clientes de verdad.
- **Pasos manuales del viernes 2026-11-27** (en su servidor/PC cuando tenga
  luz): generar una `DJANGO_SECRET_KEY` nueva para el `.env` de la web,
  arrancar la web en el puerto 8001 y cambiar los routers guardados de
  8728 a 8729 con api-ssl habilitado. Esos pasos siguen pendientes y no
  los cubre este cambio.

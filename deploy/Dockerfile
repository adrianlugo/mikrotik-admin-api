# Dockerfile de ejemplo para correr la API en un servidor con Docker.
#
# OPCIONAL: solo para cuando haya un servidor. En local en la PC se sigue
# usando runserver y no hace falta Docker. Ver docs/deployment.md.
#
# Construir y arrancar (desde la raíz del repo):
#   docker build -t mikrotik-admin-api -f deploy/Dockerfile .
#   docker run --rm -p 127.0.0.1:8000:8000 --env-file .env \
#     -v mikrotik-datos:/app/datos mikrotik-admin-api
# La base SQLite vive en /app/datos/db.sqlite3 dentro del volumen, para
# que no se pierda al recrear el contenedor. En producción con más carga,
# mejor PostgreSQL (ver docs/deployment.md).

FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DJANGO_DEBUG=false
# La base y los respaldos van en /app/datos (volumen).
ENV DJANGO_DATABASE_NAME=/app/datos/db.sqlite3
RUN mkdir -p /app/datos /app/logs /app/staticfiles \
    && DJANGO_SECRET_KEY=clave-desechable-solo-para-el-build \
       python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60"]

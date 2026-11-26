"""Respaldo de la base de datos SQLite.

Copia ``db.sqlite3`` a ``backups/`` con la fecha y hora en el nombre y
conserva las últimas copias (por defecto 7). Es el respaldo pensado para
el uso en local en la PC de Adrián: una copia del archivo basta para
recuperar clientes, planes y facturas.

Uso (desde la carpeta del proyecto, con el venv activado):

    python manage.py respaldar_bd
    python manage.py respaldar_bd --destino C:\\respaldos --conservar 14

Si algún día la base pasa a PostgreSQL, este comando no sirve: ahí el
respaldo es con ``pg_dump`` (ver docs/deployment.md).
"""

import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Copia la base de datos SQLite a backups/ con fecha y hora.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--destino',
            default=str(settings.BASE_DIR / 'backups'),
            help='Carpeta donde guardar la copia (por defecto, backups/).',
        )
        parser.add_argument(
            '--conservar',
            type=int,
            default=7,
            help='Cuántas copias recientes conservar (por defecto, 7).',
        )

    def handle(self, *args, **options):
        conservar = options['conservar']
        if conservar is None or conservar < 1:
            # 0 o negativo borraría TODAS las copias (o ninguna, según el
            # código viejo): se rechaza con un error claro.
            raise CommandError('--conservar debe ser mayor que 0 (por ejemplo, 7).')
        base_datos = settings.DATABASES['default']
        if base_datos['ENGINE'] != 'django.db.backends.sqlite3':
            raise CommandError(
                'Este respaldo solo sirve para SQLite. Con PostgreSQL usa '
                'pg_dump (ver docs/deployment.md).'
            )
        origen = Path(base_datos['NAME'])
        if not origen.exists():
            # Sin la ruta interna: es un dato del servidor, no del usuario.
            raise CommandError('No existe la base de datos configurada.')
        destino = Path(options['destino'])
        destino.mkdir(parents=True, exist_ok=True)
        marca = datetime.now().strftime('%Y%m%d-%H%M%S')
        copia = destino / f"{origen.stem}-{marca}{origen.suffix}"
        shutil.copy2(origen, copia)
        # Limpieza: se quedan solo las copias más recientes.
        copias = sorted(destino.glob(f"{origen.stem}-*{origen.suffix}"))
        for vieja in copias[:-conservar]:
            vieja.unlink()
        self.stdout.write(self.style.SUCCESS(f'Respaldo guardado en {copia}'))

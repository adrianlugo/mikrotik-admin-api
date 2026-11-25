"""Cifra en reposo las credenciales guardadas en texto plano.

Uso (después de configurar MIKROTIK_CREDENTIALS_KEY en el entorno):

    python manage.py cifrar_credenciales

Recorre todos los routers y clientes PPPoE y cifra las contraseñas que
todavía están en texto plano. Las que ya están cifradas se dejan intactas.
Sin la variable de entorno configurada el comando no hace nada y falla con
un error claro: cifrar sin clave no tiene sentido y perder la clave deja
las credenciales inaccesibles (ver docs/security.md).
"""

from django.core.management.base import BaseCommand, CommandError

from api_mikrotik.crypto import PREFIX, encryption_configured
from api_mikrotik.models import ClientePPPoE, Router


class Command(BaseCommand):
    help = 'Cifra las contraseñas de routers y clientes PPPoE guardadas en texto plano.'

    def handle(self, *args, **options):
        if not encryption_configured():
            raise CommandError(
                'MIKROTIK_CREDENTIALS_KEY no está configurada. Define la clave '
                'en el entorno y vuelve a intentarlo (ver .env.example y '
                'docs/security.md).'
            )

        routers = 0
        for router in Router.objects.all():
            if router.password and not router.password.startswith(PREFIX):
                # save() cifra el valor automáticamente.
                router.save(update_fields=['password'])
                routers += 1

        clientes = 0
        for cliente in ClientePPPoE.objects.all():
            if cliente.password_pppoe and not cliente.password_pppoe.startswith(PREFIX):
                cliente.save(update_fields=['password_pppoe'])
                clientes += 1

        self.stdout.write(self.style.SUCCESS(
            f'Credenciales cifradas: {routers} routers, {clientes} clientes PPPoE.'
        ))

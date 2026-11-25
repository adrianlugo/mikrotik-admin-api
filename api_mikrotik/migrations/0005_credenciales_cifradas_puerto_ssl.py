# Migración generada a mano para fix/critical-security-2026-11-25.
#
# Solo cambia la longitud de los campos de contraseña (los valores cifrados
# con Fernet son más largos que el texto plano) y el puerto por defecto de
# la API RouterOS a 8729 (API-SSL). NO cifra ni modifica los valores ya
# guardados: las contraseñas en texto plano siguen funcionando y se cifran
# al reintroducirlas o con `python manage.py cifrar_credenciales` una vez
# configurada MIKROTIK_CREDENTIALS_KEY (ver docs/security.md).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api_mikrotik', '0004_clientered_interfaz_mikrotik_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='router',
            name='puerto_api',
            field=models.IntegerField(
                default=8729,
                help_text='Puerto de la API RouterOS: 8729 (API-SSL, recomendado) o 8728 (sin cifrar, solo laboratorio)',
            ),
        ),
        migrations.AlterField(
            model_name='router',
            name='password',
            field=models.CharField(
                help_text='Contraseña de la API del router. Se cifra en reposo cuando MIKROTIK_CREDENTIALS_KEY está configurada.',
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name='clientepppoe',
            name='password_pppoe',
            field=models.CharField(
                help_text='Password para el secret. Se cifra en reposo cuando MIKROTIK_CREDENTIALS_KEY está configurada.',
                max_length=255,
            ),
        ),
    ]

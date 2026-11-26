# Migración generada a mano para fix/perfil-local-pool-2026-11-25.
#
# Añade a PlanVelocidad los dos datos del perfil PPPoE que faltaban para
# que la API pueda crear un perfil completo en el router:
# - direccion_local: IP del loopback de ese router (local-address).
# - pool_remoto: nombre del pool de clientes (remote-address).
# Ambos son opcionales: los planes ya guardados quedan con esos campos
# vacíos y la API no toca el local-address ni el remote-address de los
# perfiles que ya existen en el router.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api_mikrotik', '0005_credenciales_cifradas_puerto_ssl'),
    ]

    operations = [
        migrations.AddField(
            model_name='planvelocidad',
            name='direccion_local',
            field=models.GenericIPAddressField(
                blank=True,
                help_text='IP local del perfil PPPoE (local-address): la dirección IP del loopback de este router. Es distinta en cada router.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='planvelocidad',
            name='pool_remoto',
            field=models.CharField(
                blank=True,
                help_text='Nombre del pool de direcciones del perfil PPPoE (remote-address), por ejemplo pool-pppoe.',
                max_length=100,
            ),
        ),
    ]

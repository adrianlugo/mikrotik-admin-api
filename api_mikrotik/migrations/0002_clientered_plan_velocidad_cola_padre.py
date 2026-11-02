from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api_mikrotik', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='planvelocidad',
            name='cola_padre',
            field=models.CharField(blank=True, help_text='Nombre de la cola padre en MikroTik', max_length=100),
        ),
        migrations.CreateModel(
            name='ClienteRed',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=200)),
                ('tipo', models.CharField(choices=[('dhcp', 'DHCP'), ('ip_fija', 'IP fija')], max_length=20)),
                ('direccion_ip', models.GenericIPAddressField()),
                ('direccion_mac', models.CharField(blank=True, max_length=17)),
                ('cola_mikrotik', models.CharField(blank=True, max_length=100)),
                ('routeros_id', models.CharField(blank=True, max_length=100)),
                ('estado', models.CharField(choices=[('activo', 'Activo'), ('suspendido', 'Suspendido')], default='activo', max_length=20)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='clientes_red', to='api_mikrotik.planvelocidad')),
                ('router', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='clientes_red', to='api_mikrotik.router')),
            ],
            options={'ordering': ('nombre',)},
        ),
        migrations.AddConstraint(
            model_name='clientered',
            constraint=models.UniqueConstraint(fields=('router', 'direccion_ip'), name='cliente_red_router_ip_unica'),
        ),
    ]

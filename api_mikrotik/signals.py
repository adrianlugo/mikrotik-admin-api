from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PerfilUsuario


@receiver(post_save, sender=get_user_model())
def crear_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        rol = 'administrador' if instance.is_superuser else 'lectura'
        PerfilUsuario.objects.get_or_create(usuario=instance, defaults={'rol': rol})

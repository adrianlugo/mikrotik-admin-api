from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import (
    ClientePPPoE,
    ClienteRed,
    Factura,
    Pago,
    PerfilUsuario,
    PlanVelocidad,
    Router,
)


class PerfilUsuarioInline(admin.StackedInline):
    model = PerfilUsuario
    can_delete = False
    verbose_name_plural = 'Perfil operativo'


class UsuarioConPerfilAdmin(UserAdmin):
    inlines = (PerfilUsuarioInline,)


admin.site.unregister(User)
admin.site.register(User, UsuarioConPerfilAdmin)

@admin.register(Router)
class RouterAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'ip_address', 'puerto_api', 'activo', 'creado_en')
    list_filter = ('activo',)
    search_fields = ('nombre', 'ip_address')

@admin.register(PlanVelocidad)
class PlanVelocidadAdmin(admin.ModelAdmin):
    list_display = ('nombre_perfil', 'subida_mbps', 'bajada_mbps', 'direccion_local', 'pool_remoto', 'router')
    list_filter = ('router',)
    search_fields = ('nombre_perfil', 'pool_remoto')

@admin.register(ClientePPPoE)
class ClientePPPoEAdmin(admin.ModelAdmin):
    list_display = ('usuario_pppoe', 'nombre_completo', 'router', 'plan', 'estado', 'creado_en')
    list_filter = ('estado', 'router', 'plan')
    search_fields = ('usuario_pppoe', 'nombre_completo')

@admin.register(ClienteRed)
class ClienteRedAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'direccion_ip', 'direccion_mac', 'interfaz_mikrotik', 'servidor_dhcp', 'router', 'plan', 'cola_mikrotik', 'estado')
    list_filter = ('tipo', 'estado', 'router', 'plan')
    search_fields = ('nombre', 'direccion_ip', 'direccion_mac')


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'rol')
    list_filter = ('rol',)
    search_fields = ('usuario__username', 'usuario__email')


@admin.register(Factura)
class FacturaAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'periodo', 'monto', 'fecha_vencimiento', 'estado')
    list_filter = ('estado', 'periodo')
    search_fields = ('cliente__nombre_completo', 'cliente__usuario_pppoe')
    date_hierarchy = 'fecha_vencimiento'


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ('id', 'factura', 'monto', 'metodo', 'registrado_por', 'registrado_en')
    list_filter = ('metodo', 'registrado_en')
    search_fields = ('factura__cliente__nombre_completo', 'referencia')

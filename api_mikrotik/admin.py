from django.contrib import admin
from .models import Router, PlanVelocidad, ClientePPPoE

@admin.register(Router)
class RouterAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'ip_address', 'puerto_api', 'activo', 'creado_en')
    list_filter = ('activo',)
    search_fields = ('nombre', 'ip_address')

@admin.register(PlanVelocidad)
class PlanVelocidadAdmin(admin.ModelAdmin):
    list_display = ('nombre_perfil', 'subida_mbps', 'bajada_mbps', 'router')
    list_filter = ('router',)
    search_fields = ('nombre_perfil',)

@admin.register(ClientePPPoE)
class ClientePPPoEAdmin(admin.ModelAdmin):
    list_display = ('usuario_pppoe', 'nombre_completo', 'router', 'plan', 'estado', 'creado_en')
    list_filter = ('estado', 'router', 'plan')
    search_fields = ('usuario_pppoe', 'nombre_completo')

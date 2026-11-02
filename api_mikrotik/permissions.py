from rest_framework.permissions import BasePermission, SAFE_METHODS


def obtener_rol(usuario):
    if not usuario or not usuario.is_authenticated:
        return None
    if usuario.is_superuser or usuario.is_staff:
        return 'administrador'
    perfil = getattr(usuario, 'perfil_operativo', None)
    return perfil.rol if perfil else 'lectura'


class EsAdministrador(BasePermission):
    def has_permission(self, request, view):
        return obtener_rol(request.user) == 'administrador'


class PuedeOperarClientes(BasePermission):
    def has_permission(self, request, view):
        return obtener_rol(request.user) in ('administrador', 'tecnico')


class PermisoOperativo(BasePermission):
    """Lectura para todos; administración para administrador/técnico según método."""

    def has_permission(self, request, view):
        rol = obtener_rol(request.user)
        if rol == 'administrador':
            return True
        if rol == 'tecnico' and request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return True
        if rol == 'tecnico':
            return getattr(view, 'permite_tecnico_edicion', False)
        return request.method in SAFE_METHODS and rol == 'lectura'

from django.db import models

class Router(models.Model):
    """Guarda la información de conexión de cada MikroTik en tu red"""
    nombre = models.CharField(max_length=100, unique=True)
    ip_address = models.GenericIPAddressField(unique=True)
    puerto_api = models.IntegerField(default=8728) # 8728 por defecto para v6, u otro para REST v7
    usuario = models.CharField(max_length=50)
    password = models.CharField(max_length=128) # Almacenado de forma segura en producción
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} ({self.ip_address})"

class PlanVelocidad(models.Model):
    """Mapea los Profiles de MikroTik (ej: 10Megas_Plan)"""
    router = models.ForeignKey(Router, on_delete=models.CASCADE, related_name='planes')
    nombre_perfil = models.CharField(max_length=100) # Nombre exacto del Profile en MikroTik
    cola_padre = models.CharField(max_length=100, blank=True, help_text="Nombre de la cola padre en MikroTik")
    subida_mbps = models.IntegerField(help_text="Velocidad de subida en Mbps")
    bajada_mbps = models.IntegerField(help_text="Velocidad de bajada en Mbps")

    class Meta:
        unique_together = ('router', 'nombre_perfil')

    def __str__(self):
        return f"{self.nombre_perfil} - {self.router.nombre}"

class ClientePPPoE(models.Model):
    """Registro local de los clientes y sus credenciales de conexión"""
    ESTADOS = (
        ('activo', 'Activo'),
        ('suspendido', 'Suspendido'),
    )
    
    router = models.ForeignKey(Router, on_delete=models.PROTECT)
    plan = models.ForeignKey(PlanVelocidad, on_delete=models.PROTECT)
    usuario_pppoe = models.CharField(max_length=100, unique=True, help_text="User para el secret")
    password_pppoe = models.CharField(max_length=100, help_text="Password para el secret")
    nombre_completo = models.CharField(max_length=200)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='activo')
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usuario_pppoe} - {self.nombre_completo}"


class ClienteRed(models.Model):
    """Cliente identificado por MAC/IP para DHCP o configuración IP fija."""
    TIPOS = (
        ('dhcp', 'DHCP'),
        ('ip_fija', 'IP fija'),
    )
    ESTADOS = (
        ('activo', 'Activo'),
        ('suspendido', 'Suspendido'),
    )

    router = models.ForeignKey(Router, on_delete=models.PROTECT, related_name='clientes_red')
    plan = models.ForeignKey(PlanVelocidad, on_delete=models.PROTECT, related_name='clientes_red')
    nombre = models.CharField(max_length=200)
    tipo = models.CharField(max_length=20, choices=TIPOS)
    direccion_ip = models.GenericIPAddressField()
    direccion_mac = models.CharField(max_length=17, blank=True)
    cola_mikrotik = models.CharField(max_length=100, blank=True)
    routeros_id = models.CharField(max_length=100, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='activo')
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('router', 'direccion_ip'), name='cliente_red_router_ip_unica'),
        ]
        ordering = ('nombre',)

    def __str__(self):
        return f"{self.nombre} ({self.direccion_ip})"

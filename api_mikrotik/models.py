import uuid

from django.conf import settings
from django.db import models


class PerfilUsuario(models.Model):
    ROLES = (
        ('administrador', 'Administrador'),
        ('tecnico', 'Técnico/Soporte'),
        ('lectura', 'Solo lectura'),
    )

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='perfil_operativo')
    rol = models.CharField(max_length=20, choices=ROLES, default='lectura')

    def __str__(self):
        return f"{self.usuario.get_username()} ({self.get_rol_display()})"

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
    direccion_ip_antena = models.GenericIPAddressField(blank=True, null=True, help_text="IP del equipo o antena que sirve al cliente")
    portal_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    interfaz_mikrotik = models.CharField(max_length=100, blank=True, default='bridge-general', help_text='Interfaz de LAN usada para reservas ARP estáticas e IP fija')
    servidor_dhcp = models.CharField(max_length=100, blank=True, help_text='Nombre opcional del servidor DHCP; déjalo vacío si solo existe uno')
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


class Factura(models.Model):
    ESTADOS = (
        ('pendiente', 'Pendiente'),
        ('pagada', 'Pagada'),
        ('vencida', 'Vencida'),
        ('anulada', 'Anulada'),
    )

    cliente = models.ForeignKey(ClientePPPoE, on_delete=models.PROTECT, related_name='facturas')
    periodo = models.DateField(help_text="Primer día del mes facturado")
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_emision = models.DateField(auto_now_add=True)
    fecha_vencimiento = models.DateField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    observaciones = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('cliente', 'periodo'), name='factura_cliente_periodo_unica'),
        ]
        ordering = ('-fecha_vencimiento',)

    def __str__(self):
        return f"Factura {self.id} - {self.cliente.nombre_completo}"


class Pago(models.Model):
    METODOS = (
        ('efectivo', 'Efectivo'),
        ('transferencia', 'Transferencia'),
        ('tarjeta', 'Tarjeta'),
        ('otro', 'Otro'),
    )

    factura = models.ForeignKey(Factura, on_delete=models.CASCADE, related_name='pagos')
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    metodo = models.CharField(max_length=20, choices=METODOS)
    referencia = models.CharField(max_length=100, blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    registrado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Pago {self.id} - {self.factura_id}"

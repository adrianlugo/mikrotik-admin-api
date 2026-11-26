import uuid

from django.conf import settings
from django.db import models

from .crypto import decrypt_value, encrypt_value


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
    puerto_api = models.IntegerField(default=8729, help_text="Puerto de la API RouterOS: 8729 (API-SSL, recomendado) o 8728 (sin cifrar, solo laboratorio)")
    usuario = models.CharField(max_length=50)
    password = models.CharField(max_length=255, help_text="Contraseña de la API del router. Se cifra en reposo cuando MIKROTIK_CREDENTIALS_KEY está configurada.")
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def get_password(self):
        """Devuelve la contraseña de la API descifrada (o en texto plano si es una credencial antigua sin cifrar)."""
        return decrypt_value(self.password)

    def save(self, *args, **kwargs):
        if self.password:
            self.password = encrypt_value(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} ({self.ip_address})"

class PlanVelocidad(models.Model):
    """Mapea los Profiles de MikroTik (ej: 10Megas_Plan)"""
    router = models.ForeignKey(Router, on_delete=models.CASCADE, related_name='planes')
    nombre_perfil = models.CharField(max_length=100) # Nombre exacto del Profile en MikroTik
    cola_padre = models.CharField(max_length=100, blank=True, help_text="Nombre de la cola padre en MikroTik")
    subida_mbps = models.IntegerField(help_text="Velocidad de subida en Mbps")
    bajada_mbps = models.IntegerField(help_text="Velocidad de bajada en Mbps")
    # Dirección local del perfil PPPoE (local-address): la IP del loopback
    # de ESTE router. Es distinta en cada router, por eso se guarda por plan
    # (cada plan pertenece a un router). Opcional: si se deja vacía, la API
    # no toca el local-address del perfil que ya existe en el router.
    direccion_local = models.GenericIPAddressField(
        blank=True, null=True,
        help_text="IP local del perfil PPPoE (local-address): la dirección IP del loopback de este router. Es distinta en cada router.",
    )
    # Pool de direcciones del perfil PPPoE (remote-address): el nombre del
    # pool del que salen las IPs de los clientes, por ejemplo pool-pppoe.
    # Opcional: si se deja vacío, la API no toca el remote-address del
    # perfil que ya existe en el router.
    pool_remoto = models.CharField(
        max_length=100, blank=True,
        help_text="Nombre del pool de direcciones del perfil PPPoE (remote-address), por ejemplo pool-pppoe.",
    )

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
    password_pppoe = models.CharField(max_length=255, help_text="Password para el secret. Se cifra en reposo cuando MIKROTIK_CREDENTIALS_KEY está configurada.")
    nombre_completo = models.CharField(max_length=200)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='activo')
    direccion_ip_antena = models.GenericIPAddressField(blank=True, null=True, help_text="IP del equipo o antena que sirve al cliente")
    portal_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    def get_password_pppoe(self):
        """Devuelve la contraseña PPPoE descifrada (o en texto plano si es una credencial antigua sin cifrar)."""
        return decrypt_value(self.password_pppoe)

    def save(self, *args, **kwargs):
        if self.password_pppoe:
            self.password_pppoe = encrypt_value(self.password_pppoe)
        super().save(*args, **kwargs)

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

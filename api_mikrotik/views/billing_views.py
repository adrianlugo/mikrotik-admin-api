from rest_framework import viewsets
from drf_spectacular.utils import extend_schema, extend_schema_view

from api_mikrotik.models import Factura, Pago
from api_mikrotik.serializers import FacturaSerializer, PagoSerializer
from api_mikrotik.permissions import PermisoOperativo


@extend_schema_view(
    list=extend_schema(summary="Listar facturas", tags=['Facturación']),
    retrieve=extend_schema(summary="Consultar una factura", tags=['Facturación']),
    create=extend_schema(summary="Crear una factura", tags=['Facturación']),
    update=extend_schema(summary="Actualizar una factura", tags=['Facturación']),
    partial_update=extend_schema(summary="Actualizar parcialmente una factura", tags=['Facturación']),
    destroy=extend_schema(summary="Eliminar una factura", tags=['Facturación']),
)
class FacturaViewSet(viewsets.ModelViewSet):
    queryset = Factura.objects.select_related('cliente').all()
    serializer_class = FacturaSerializer
    permission_classes = [PermisoOperativo]


@extend_schema_view(
    list=extend_schema(summary="Listar pagos", tags=['Pagos']),
    retrieve=extend_schema(summary="Consultar un pago", tags=['Pagos']),
    create=extend_schema(summary="Registrar un pago", tags=['Pagos']),
    update=extend_schema(summary="Actualizar un pago", tags=['Pagos']),
    partial_update=extend_schema(summary="Actualizar parcialmente un pago", tags=['Pagos']),
    destroy=extend_schema(summary="Eliminar un pago", tags=['Pagos']),
)
class PagoViewSet(viewsets.ModelViewSet):
    queryset = Pago.objects.select_related('factura').all()
    serializer_class = PagoSerializer
    permission_classes = [PermisoOperativo]

    def actualizar_estado_factura(self, factura):
        if factura.estado == 'anulada':
            return
        pagado = sum((item.monto for item in factura.pagos.all()), 0)
        nuevo_estado = 'pagada' if pagado >= factura.monto else 'pendiente'
        if factura.estado != nuevo_estado:
            factura.estado = nuevo_estado
            factura.save(update_fields=['estado', 'actualizado_en'])

    def perform_create(self, serializer):
        pago = serializer.save(registrado_por=self.request.user)
        self.actualizar_estado_factura(pago.factura)

    def perform_update(self, serializer):
        pago = serializer.save()
        self.actualizar_estado_factura(pago.factura)

    def perform_destroy(self, instance):
        factura = instance.factura
        instance.delete()
        self.actualizar_estado_factura(factura)
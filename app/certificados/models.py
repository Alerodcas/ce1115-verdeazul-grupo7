import uuid

from django.conf import settings
from django.db import models


class PeriodoMedida(models.Model):
    """ Representa el período de medición de biomasa (ej. 2026-I). 
    La Gerencia de Certificación gestiona su estado 
    ('ABIERTO' / 'CERRADO') [1, 3]. """

    STATUS_CHOICES = [('ABIERTO', 'Abierto'), ('CERRADO', 'Cerrado')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, help_text="Ej: Período de Medición 2026-I")
    year = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ABIERTO')
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT, 
        related_name='periodos_modificados',
        null=True, 
        blank=True
    )

    class Meta: 
        verbose_name = "Periodo de Medición"
        verbose_name_plural = "Periodos de Medición"
        ordering = ['-year', '-start_date']

    def __str__(self):
        return f"{self.name} [{self.status}]"

class Certificado(models.Model):

    STATUS_CHOICES = [('VIGENTE', 'Vigente'), ('REVOCADO', 'Revocado')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    period = models.ForeignKey(
        PeriodoMedida,
        on_delete=models.PROTECT,
        related_name='certificados'
    )
    finca_id = models.UUIDField(help_text="Identificador único de la finca certificada") 
    parcela_id = models.CharField(max_length=100, help_text="Identificador de la parcela/hectárea") 
    tons_co2 = models.DecimalField(max_digits=12, decimal_places=2, help_text="Toneladas de CO2 capturadas")

    emitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT,
        related_name='certificados_firmados'
    )

    emitted_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='VIGENTE')
    revocation_reasons = models.TextField(blank=True)

    canonical_data = models.JSONField(help_text="Payload JSON Estructurado que fue firmado")
    sign_digital = models.TextField(help_text="Firma digital RSA-SHA256 en Base64")
    public_key_pem = models.TextField(help_text="Clave pública PEM correspondiente incrustada")

    class Meta: 
        verbose_name = "Certificado de Carbono" 
        verbose_name_plural = "Certificados de Carbono" # Garantiza que no se emita más de un certificado vigente sobre la misma parcela y período (Regla C3) [2, 5] 
        constraints = [
            models.UniqueConstraint(
                fields=["finca_id", "parcela_id", "period"],
                condition=models.Q(status="VIGENTE"),
                name="unique_certificado_vigente_por_parcela_periodo",
            )
        ]

    def __str__(self):
        return f"Certificado {self.id} - Finca {self.finca_id} ({self.tons_co2} tCO2)"

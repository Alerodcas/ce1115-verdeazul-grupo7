"""Entidades del negocio (docs/CONTRATO-DATOS.md §2).

Dueño: Daniel. La bitácora (`Bitacora`) vive en la app `auditoria`.

Reglas que este módulo sostiene a nivel de base de datos, porque son las que no
deben depender de que cada vista se acuerde de comprobarlas:

* Ningún objeto se borra (Parte 1: trazabilidad por diez años). `delete()` y el
  borrado en lote levantan `ProtectedOperation`; las claves foráneas son
  `PROTECT`. Lo que sale de circulación se desactiva o cambia de estado.
* Un solo certificado vigente por finca y período (regla C3).
* El ejecutor y el aprobador de una cuenta son personas distintas (regla C6).

Los atributos que consume el PDP (`es_autor`, `fue_editor`, `estado_objeto`...)
se leen de estos campos, nunca del cuerpo de la petición.
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

Usuario = settings.AUTH_USER_MODEL


class ProtectedOperation(Exception):
    """Se intentó borrar un objeto que, por diseño, no se borra."""


class _SinBorradoQuerySet(models.QuerySet):
    def delete(self):
        raise ProtectedOperation("Los objetos de negocio no se borran.")


class SinBorrado(models.Model):
    objects = _SinBorradoQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise ProtectedOperation(
            f"{type(self).__name__} no se borra: se desactiva o cambia de estado."
        )


class Finca(SinBorrado):
    nombre = models.CharField(max_length=120)
    ubicacion = models.CharField(max_length=255, blank=True)
    area_ha = models.DecimalField(max_digits=10, decimal_places=2)
    propietario = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="fincas_propias"
    )  # regla S2
    tecnicos = models.ManyToManyField(
        Usuario, blank=True, related_name="fincas_asignadas"
    )  # regla S1
    activa = models.BooleanField(default=True)  # Deactivate, nunca Delete
    creada_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre


class Periodo(SinBorrado):
    etiqueta = models.CharField(max_length=30, unique=True)
    inicio = models.DateField()
    fin = models.DateField()
    abierto = models.BooleanField(default=False)  # solo la Gerencia: Open / Close

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(fin__gt=F("inicio")), name="periodo_fin_posterior"
            )
        ]

    def __str__(self):
        return self.etiqueta


class Medicion(SinBorrado):
    class Estado(models.TextChoices):
        BORRADOR = "borrador"
        ENVIADA = "enviada"
        DEVUELTA = "devuelta"
        APROBADA = "aprobada"

    finca = models.ForeignKey(Finca, on_delete=models.PROTECT, related_name="mediciones")
    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name="mediciones")
    # Una enmienda no sobrescribe: crea una versión nueva que apunta a la anterior.
    version = models.PositiveIntegerField(default=1)
    reemplaza = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reemplazada_por"
    )
    valor = models.DecimalField(max_digits=14, decimal_places=3)
    unidad = models.CharField(max_length=20, default="tCO2e")
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.BORRADOR)
    creada_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="mediciones_creadas"
    )  # es_autor
    editores = models.ManyToManyField(
        Usuario, blank=True, related_name="mediciones_editadas"
    )  # fue_editor (regla C2: quien editó no aprueba)
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["finca", "periodo", "version"], name="medicion_version_unica"
            )
        ]


class Enmienda(SinBorrado):
    class Estado(models.TextChoices):
        SOLICITADA = "solicitada"
        AUTORIZADA = "autorizada"
        RECHAZADA = "rechazada"
        APLICADA = "aplicada"

    medicion = models.ForeignKey(Medicion, on_delete=models.PROTECT, related_name="enmiendas")
    solicitante = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="enmiendas_solicitadas"
    )
    autorizante = models.ForeignKey(
        Usuario, null=True, blank=True, on_delete=models.PROTECT,
        related_name="enmiendas_autorizadas",
    )
    motivo = models.TextField()
    valor_propuesto = models.DecimalField(max_digits=14, decimal_places=3)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.SOLICITADA)
    medicion_nueva = models.OneToOneField(
        Medicion, null=True, blank=True, on_delete=models.PROTECT, related_name="origen_enmienda"
    )
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(autorizante__isnull=True) | ~Q(autorizante=F("solicitante")),
                name="enmienda_autorizante_distinto",
            )
        ]


class Certificado(SinBorrado):
    class Estado(models.TextChoices):
        VIGENTE = "vigente"
        REVOCADO = "revocado"

    finca = models.ForeignKey(Finca, on_delete=models.PROTECT, related_name="certificados")
    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name="certificados")
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.VIGENTE)
    emitido_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="certificados_emitidos"
    )
    emitido_en = models.DateTimeField(auto_now_add=True)
    revocado_por = models.ForeignKey(
        Usuario, null=True, blank=True, on_delete=models.PROTECT,
        related_name="certificados_revocados",
    )
    revocado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            # Regla C3. Índice único parcial en lugar de restricción de exclusión
            # para que las pruebas corran igual en SQLite (CONTRATO §6.5).
            models.UniqueConstraint(
                fields=["finca", "periodo"],
                condition=Q(estado="vigente"),
                name="un_certificado_vigente_por_finca_periodo",
            )
        ]


class Cuenta(SinBorrado):
    """Gestión de una cuenta de usuario: solicitud escrita y doble control (C6)."""

    class Estado(models.TextChoices):
        SOLICITADA = "solicitada"
        AUTORIZADA = "autorizada"
        EJECUTADA = "ejecutada"
        REVOCADA = "revocada"

    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="cuentas_gestionadas")
    rol_solicitado = models.CharField(max_length=40)
    solicitud = models.TextField()  # la solicitud escrita
    solicitante = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="cuentas_solicitadas"
    )
    ejecutor = models.ForeignKey(
        Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="cuentas_ejecutadas"
    )
    aprobador = models.ForeignKey(
        Usuario, null=True, blank=True, on_delete=models.PROTECT, related_name="cuentas_aprobadas"
    )
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.SOLICITADA)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(ejecutor__isnull=True)
                | Q(aprobador__isnull=True)
                | ~Q(ejecutor=F("aprobador")),
                name="cuenta_ejecutor_distinto_de_aprobador",
            )
        ]

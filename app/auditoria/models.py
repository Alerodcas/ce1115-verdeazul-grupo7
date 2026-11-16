"""Bitácora de auditoría (Parte 1; docs/CONTRATO-DATOS.md, objeto `Bitacora`).

Qué sostiene este módulo (las capas que caben en Cloud Run + Neon, ver
docs/DESVIACIONES.md D-03):

* **Solo inserción**, en dos niveles: el modelo rechaza `save()` sobre una fila
  existente, `delete()` y los `update()`/`delete()` en lote; y la migración
  instala un disparador en la base que aborta cualquier UPDATE o DELETE.
* **Cadena de hashes**: cada entrada incluye el hash de la anterior. Alterar o
  quitar una fila rompe la cadena desde ahí (ver `servicio.verificar_cadena`).
* **Sin bifurcaciones**: `hash_previo` es único, así que dos entradas no pueden
  colgar de la misma anterior aunque dos peticiones lleguen a la vez.

Lo que NO cubre, y es la desviación D-03: quien controle toda la base puede
recalcular la cadena. Para eso estaban las capas 3 y 4, que no se desplegaron.
"""

from django.db import models

GENESIS = "0" * 64


class ErrorBitacora(Exception):
    """No se pudo escribir en la bitácora. Quien llama debe fallar cerrado."""


class BitacoraInmutable(ErrorBitacora):
    """Se intentó modificar o borrar una entrada."""


class _SoloInsercionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise BitacoraInmutable("La bitácora es de solo inserción.")

    def delete(self):
        raise BitacoraInmutable("La bitácora es de solo inserción.")

    def bulk_update(self, *args, **kwargs):
        raise BitacoraInmutable("La bitácora es de solo inserción.")


class Bitacora(models.Model):
    class Resultado(models.TextChoices):
        EXITO = "exito"
        DENEGADO = "denegado"
        FALLO = "fallo"

    ocurrido_en = models.DateTimeField()
    # Texto y no clave foránea: la entrada debe sobrevivir a cualquier cambio en
    # la tabla de usuarios, y registrar también a quien no está autenticado.
    actor = models.CharField(max_length=64)  # id del usuario, o "anonimo"
    rol_activo = models.CharField(max_length=40, blank=True)
    accion = models.CharField(max_length=40)  # Create, Approve, ... o AUTH.LOGIN
    objeto_tipo = models.CharField(max_length=40, blank=True)
    objeto_id = models.CharField(max_length=64, blank=True)
    resultado = models.CharField(max_length=10, choices=Resultado.choices)
    rule_id = models.CharField(max_length=60, blank=True)  # del PDP
    rule_ver = models.CharField(max_length=20, blank=True)  # del PDP
    motivo = models.CharField(max_length=255, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    detalle = models.JSONField(default=dict, blank=True)
    hash_previo = models.CharField(max_length=64, unique=True)
    hash = models.CharField(max_length=64, unique=True)

    objects = _SoloInsercionQuerySet.as_manager()

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["actor", "ocurrido_en"]),
            models.Index(fields=["objeto_tipo", "objeto_id"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            raise BitacoraInmutable("La bitácora es de solo inserción.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise BitacoraInmutable("La bitácora es de solo inserción.")

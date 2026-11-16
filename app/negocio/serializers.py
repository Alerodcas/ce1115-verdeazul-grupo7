from rest_framework import serializers

from .models import Finca, Medicion, Periodo


class FincaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Finca
        fields = ["id", "nombre", "ubicacion", "area_ha", "propietario", "activa", "creada_en"]
        read_only_fields = ["id", "activa", "creada_en"]


class FincaActualizarSerializer(FincaSerializer):
    """El propietario no cambia por esta vía."""

    class Meta(FincaSerializer.Meta):
        read_only_fields = [*FincaSerializer.Meta.read_only_fields, "propietario"]


class PeriodoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Periodo
        fields = ["id", "etiqueta", "inicio", "fin", "abierto"]
        read_only_fields = fields


class MedicionSerializer(serializers.ModelSerializer):
    """Del cliente solo entran finca, período, valor y unidad.

    Estado, versión, autor y editores los fija el servidor: son los hechos que la
    política lee, y no pueden venir en la petición.
    """

    class Meta:
        model = Medicion
        fields = [
            "id", "finca", "periodo", "version", "valor", "unidad", "estado",
            "creada_por", "creada_en", "actualizada_en",
        ]
        read_only_fields = [
            "id", "version", "estado", "creada_por", "creada_en", "actualizada_en",
        ]


class MedicionActualizarSerializer(MedicionSerializer):
    class Meta(MedicionSerializer.Meta):
        read_only_fields = [*MedicionSerializer.Meta.read_only_fields, "finca", "periodo"]

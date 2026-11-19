from rest_framework import serializers

from .models import ROLES, Cuenta, Enmienda, Finca, Medicion, Periodo


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


class EnmiendaSerializer(serializers.ModelSerializer):
    """Entran medición, motivo y valor propuesto. Lo demás lo fija el servidor."""

    class Meta:
        model = Enmienda
        fields = [
            "id", "medicion", "solicitante", "autorizante", "motivo", "valor_propuesto",
            "estado", "medicion_nueva", "creada_en",
        ]
        read_only_fields = [
            "id", "solicitante", "autorizante", "estado", "medicion_nueva", "creada_en",
        ]


class CuentaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cuenta
        fields = [
            "id", "tipo", "usuario", "rol_solicitado", "solicitud", "solicitante",
            "ejecutor", "aprobador", "estado", "creada_en",
        ]
        read_only_fields = ["id", "solicitante", "ejecutor", "aprobador", "estado", "creada_en"]

    def validate(self, datos):
        tipo = datos.get("tipo", Cuenta.Tipo.ASIGNAR_ROL)
        rol = datos.get("rol_solicitado", "")
        if tipo == Cuenta.Tipo.ASIGNAR_ROL and rol not in ROLES:
            raise serializers.ValidationError({"rol_solicitado": "Rol desconocido."})
        if tipo == Cuenta.Tipo.DESACTIVAR and rol:
            raise serializers.ValidationError({"rol_solicitado": "No aplica al desactivar."})
        if not datos.get("solicitud", "").strip():
            raise serializers.ValidationError({"solicitud": "La solicitud escrita es obligatoria."})
        return datos

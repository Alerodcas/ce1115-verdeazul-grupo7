from rest_framework import serializers

from .models import Bitacora


class BitacoraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bitacora
        fields = [
            "id", "ocurrido_en", "actor", "rol_activo", "accion", "objeto_tipo", "objeto_id",
            "resultado", "rule_id", "rule_ver", "motivo", "ip", "detalle", "hash_previo", "hash",
        ]
        read_only_fields = fields

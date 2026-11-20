from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from negocio.models import Medicion

from .crypto import verify_sign
from .models import Certificado, PeriodoMedida

User = get_user_model()


def uuid_de_finca(finca_pk) -> str:
    """UUID con el que el módulo de certificados nombra una finca del registro.

    Es el mismo patrón que arma la interfaz (certificados.js, uuidDeFinca): el número
    de la finca, en decimal, relleno con ceros en el último grupo.
    """
    return "00000000-0000-0000-0000-" + str(finca_pk).zfill(12)


class PeriodoMedidaSerializer(serializers.ModelSerializer):
    """
    Serializador para la consulta y actualización de Períodos de Medición.
    Permite a la Gerencia de Certificación abrir o cerrar períodos.
    """
    modified_by_username = serializers.ReadOnlyField(source='modified_by.username')

    class Meta:
        model = PeriodoMedida
        fields = [
            'id',
            'name',
            'year',
            'status',
            'start_date',
            'end_date',
            'modified_by',
            'modified_by_username',
        ]
        read_only_fields = ['id', 'start_date', 'modified_by', 'modified_by_username']

    def validate_status(self, value):
        if value not in ['ABIERTO', 'CERRADO']:
            raise serializers.ValidationError("El estado debe ser 'ABIERTO' o 'CERRADO'.")
        return value

    def update(self, instance, validated_data):
        new_status = validated_data.get('status', instance.status)

        #Marcar el momento del cierre del periodo en utc
        if new_status == 'CERRADO' and instance.status != 'CERRADO':
            instance.end_date = timezone.now()
        elif new_status == 'ABIERTO':
            instance.end_date = None

        instance.status = new_status
        instance.name = validated_data.get('name', instance.name)
        instance.year = validated_data.get('year', instance.year)
        instance.modified_by = self.context['request'].user
        instance.save()
        return instance


class CertificadoEmisionSerializer(serializers.ModelSerializer):
    """
    Serializador para la emisión de nuevos certificados de captura de carbono.
    Valida la apertura del período y la regla de unicidad por parcela/período (Regla C3).
    Exige la medición de origen: aprobada y de la misma finca. Que quien emite no sea su
    autor lo comprueba la vista, porque es una denegación y queda en la bitácora.
    """
    emitted_by_username = serializers.ReadOnlyField(source='emitted_by.username')
    # Solo de entrada: no se guarda en el certificado, sirve para aplicar C3 al emitir.
    medicion = serializers.PrimaryKeyRelatedField(queryset=Medicion.objects.all(), write_only=True)

    class Meta:
        model = Certificado
        fields = [
            'id',
            'medicion',
            'period',
            'finca_id',
            'parcela_id',
            'tons_co2',
            'emitted_by',
            'emitted_by_username',
            'emitted_date',
            'status',
            'canonical_data',
            'sign_digital',
            'public_key_pem',
        ]
        read_only_fields = [
            'id',
            'emitted_by',
            'emitted_by_username',
            'emitted_date',
            'status',
            'canonical_data',
            'sign_digital',
            'public_key_pem',
        ]

    def validate_tons_co2(self, value):
        if value <= 0:
            raise serializers.ValidationError("Las toneladas de CO2 deben ser un valor positivo mayor a cero.")
        return value

    def validate_medicion(self, value):
        if value.estado != Medicion.Estado.APROBADA:
            raise serializers.ValidationError("Solo se emiten certificados sobre mediciones aprobadas.")
        return value

    def validate(self, attrs):
        period = attrs.get('period')
        finca_id = attrs.get('finca_id')
        parcela_id = attrs.get('parcela_id')
        medicion = attrs.get('medicion')

        # 0. La finca del certificado es la de la medición: si no, bastaría con citar la
        #    medición de otra persona para certificar una finca cualquiera.
        if medicion and str(finca_id) != uuid_de_finca(medicion.finca_id):
            raise serializers.ValidationError({
                'finca_id': "La finca no corresponde a la medición elegida."
            })

        # 1. Validación: El período debe estar ABIERTO para emitir certificados
        if period and period.status != 'ABIERTO':
            raise serializers.ValidationError({
                'period': f"No se pueden emitir certificados en el período '{period.name}' porque se encuentra CERRADO."
            })

        # 2. Validación (Regla C3): Unicidad de certificado VIGENTE por finca, parcela y período
        if Certificado.objects.filter(
            finca_id=finca_id,
            parcela_id=parcela_id,
            period=period,
            status='VIGENTE'
        ).exists():
            raise serializers.ValidationError({
                'non_field_errors': f"Ya existe un certificado VIGENTE emitido para la parcela '{parcela_id}' de la finca {finca_id} en este período."
            })

        return attrs


class CertificadoDetailSerializer(serializers.ModelSerializer):
    """
    Serializador detallado para consultar certificados emitidos.
    Incluye los datos canónicos, la firma en Base64 y la clave pública incrustada.
    """
    period_name = serializers.ReadOnlyField(source='period.name')
    emitted_by_username = serializers.ReadOnlyField(source='emitted_by.username')

    class Meta:
        model = Certificado
        fields = [
            'id',
            'period',
            'period_name',
            'finca_id',
            'parcela_id',
            'tons_co2',
            'emitted_by',
            'emitted_by_username',
            'emitted_date',
            'status',
            'canonical_data',
            'sign_digital',
            'public_key_pem',
        ]


class CertificadoVerificacionSerializer(serializers.Serializer):
    """
    Serializador para el endpoint público de verificación de firmas de certificados.
    Permite verificar la integridad y autenticidad del certificado mediante su firma RSA-SHA256.
    """
    canonical_data = serializers.JSONField(
        required=True,
        help_text="Payload JSON del certificado a verificar."
    )
    sign_digital = serializers.CharField(
        required=True,
        help_text="Firma digital en formato Base64."
    )
    public_key_pem = serializers.CharField(
        required=True,
        help_text="Clave pública en formato PEM incrustada en el certificado."
    )

    def validate(self, attrs):
        data = attrs.get('canonical_data')
        sign = attrs.get('sign_digital')
        pub_key = attrs.get('public_key_pem')

        is_valid = verify_sign(data, sign, pub_key)
        attrs['es_valida'] = is_valid
        return attrs


class GestionCuentaUsuarioSerializer(serializers.ModelSerializer):
    """
    Serializador para la gestión de cuentas (activación / desactivación de usuarios).
    Utilizado por Administradores y Gerencia de Certificación.
    """
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'date_joined']
        read_only_fields = ['id', 'username', 'email', 'first_name', 'last_name', 'date_joined']

    def validate_is_active(self, value):
        if not isinstance(value, bool):
            raise serializers.ValidationError("El campo is_active debe ser booleano (True/False).")
        return value

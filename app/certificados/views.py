from rest_framework import viewsets, status, permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import PeriodoMedida, Certificado
from .crypto import get_private_key_pem, sign_data

from .serializers import (
    PeriodoMedidaSerializer,
    CertificadoEmisionSerializer,
    CertificadoDetailSerializer,
    CertificadoVerificacionSerializer,
    GestionCuentaUsuarioSerializer
)



User = get_user_model()

class PeriodoMedidaViewSet(viewsets.ModelViewSet):
    """
    ViewSet para listar, crear y actualizar Períodos de Medición.
    Permite a la Gerencia de Certificación abrir y cerrar períodos.
    """
    queryset = PeriodoMedida.objects.all()
    serializer_class = PeriodoMedidaSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(modified_by=self.request.user)

    def perform_update(self, serializer):
        new_status = serializer.validated_data.get('status')
        end_date = timezone.now() if new_status == 'CERRADO' else None
        serializer.save(modified_by=self.request.user, end_date=end_date)

class EsGerenciaCertificacion(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.groups.filter(name='Gerencia de Certificación').exists() or request.user.is_staff

class CertificadoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet de lectura para consultar certificados emitidos.
    """
    queryset = Certificado.objects.all()
    serializer_class = CertificadoDetailSerializer
    permission_classes = [permissions.IsAuthenticated]


class CertificadoEmisionView(generics.CreateAPIView):
    """
    Endpoint para emitir un nuevo certificado firmado digitalmente.
    POST /api/certificados/emitir/
    """
    queryset = Certificado.objects.all()
    serializer_class = CertificadoEmisionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        period = serializer.validated_data['period']
        finca_id = str(serializer.validated_data['finca_id'])
        parcela_id = serializer.validated_data['parcela_id']
        tons_co2 = float(serializer.validated_data['tons_co2'])

        # 1. Construir payload de datos canónicos para la firma
        canonical_data = {
            "period_id": str(period.id),
            "period_name": period.name,
            "finca_id": finca_id,
            "parcela_id": parcela_id,
            "tons_co2": tons_co2,
            "emitted_by": request.user.username,
            "emitted_date": timezone.now().isoformat(),
        }

        # 2. Firmar digitalmente los datos con la clave privada del sistema
        try:
            private_key_pem = get_private_key_pem()
            sign_b64, public_key_pem = sign_data(canonical_data, private_key_pem)
        except Exception as e:
            return Response(
                {"detail": f"Error al generar la firma digital: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 3. Guardar el certificado con sus firmas en la base de datos
        certificado = serializer.save(
            emitted_by=request.user,
            canonical_data=canonical_data,
            sign_digital=sign_b64,
            public_key_pem=public_key_pem
        )

        detalle_serializer = CertificadoDetailSerializer(certificado)
        return Response(detalle_serializer.data, status=status.HTTP_201_CREATED)


class CertificadoVerificacionView(APIView):
    """
    Endpoint PÚBLICO de verificación de firma de certificados.
    POST /api/certificados/verificar/
    Permite validar cualquier certificado sin requerir autenticación.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = CertificadoVerificacionSerializer(data=request.data)
        if serializer.is_valid():
            is_valid = serializer.validated_data['es_valida']
            if is_valid:
                return Response({
                    "valido": True,
                    "mensaje": "La firma digital es VÁLIDA y el contenido del certificado no ha sido alterado."
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    "valido": False,
                    "mensaje": "La firma digital es INVÁLIDA o el contenido del certificado ha sido alterado."
                }, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GestionCuentaUsuarioViewSet(viewsets.ModelViewSet):
    """
    ViewSet para la activación y desactivación de cuentas de usuario.
    PATCH/PUT /api/cuentas/<id>/
    """
    queryset = User.objects.all()
    serializer_class = GestionCuentaUsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'put', 'patch']

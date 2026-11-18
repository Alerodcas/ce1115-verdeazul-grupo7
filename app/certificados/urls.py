from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CertificadoEmisionView,
    CertificadoVerificacionView,
    CertificadoViewSet,
    GestionCuentaUsuarioViewSet,
    PeriodoMedidaViewSet,
)

app_name = 'certificados'

router = DefaultRouter()
router.register(r'periodos', PeriodoMedidaViewSet, basename='periodo')
router.register(r'certificados', CertificadoViewSet, basename='certificado')
router.register(r'cuentas', GestionCuentaUsuarioViewSet, basename='cuenta')

urlpatterns = [
    # Endpoints específicos para Certificación y Verificación
    path('emitir/', CertificadoEmisionView.as_view(), name='certificado-emitir'),
    path('verificar/', CertificadoVerificacionView.as_view(), name='certificado-verificar'),
    
    # Rutas CRUD del router (periodos/, certificados/, cuentas/)
    path('', include(router.urls)),
]

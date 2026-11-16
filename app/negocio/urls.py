from django.urls import path

from . import views as v

urlpatterns = [
    path("fincas/", v.FincaListaView.as_view()),
    path("fincas/nueva/", v.FincaCrearView.as_view()),
    path("fincas/<int:pk>/", v.FincaDetalleView.as_view()),
    path("fincas/<int:pk>/desactivar/", v.FincaDesactivarView.as_view()),
    path("periodos/", v.PeriodoListaView.as_view()),
    path("periodos/<int:pk>/abrir/", v.PeriodoAbrirView.as_view()),
    path("periodos/<int:pk>/cerrar/", v.PeriodoCerrarView.as_view()),
    path("mediciones/", v.MedicionListaView.as_view()),
    path("mediciones/nueva/", v.MedicionCrearView.as_view()),
    path("mediciones/<int:pk>/", v.MedicionDetalleView.as_view()),
    path("mediciones/<int:pk>/enviar/", v.MedicionEnviarView.as_view()),
    path("mediciones/<int:pk>/aprobar/", v.MedicionAprobarView.as_view()),
    path("mediciones/<int:pk>/devolver/", v.MedicionDevolverView.as_view()),
]

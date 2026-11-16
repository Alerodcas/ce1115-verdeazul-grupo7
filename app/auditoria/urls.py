from django.urls import path

from . import views as v

urlpatterns = [
    path("", v.BitacoraListaView.as_view()),
    path("verificar/", v.BitacoraVerificarView.as_view()),
]

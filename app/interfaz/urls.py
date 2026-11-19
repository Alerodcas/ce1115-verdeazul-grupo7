from django.urls import path

from . import views as v

app_name = "interfaz"

urlpatterns = [
    path("entrar/", v.Entrar.as_view(), name="entrar"),
    path("salir/", v.Salir.as_view(), name="salir"),
    path("rol/", v.ElegirRol.as_view(), name="rol"),
    path("segundo-factor/", v.SegundoFactor.as_view(), name="segundo_factor"),
    path("registro/", v.inicio, name="inicio"),
    # Antes de la ruta con slug: «directorio» no es una pantalla.
    path("registro/directorio/", v.directorio, name="directorio"),
    path("registro/<slug:pantalla>/", v.PantallaRegistro.as_view(), name="pantalla"),
]

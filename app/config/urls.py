"""Rutas raíz del sistema.

Cada equipo cuelga aquí su módulo. El orden no implica prioridad de seguridad:
toda vista pasa por el PEP (authz), sin excepción.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("admin/", admin.site.urls),
    # path("api/", include("negocio.urls")),        # Daniel
    # path("certificados/", include("certificados.urls")),  # Luis
    # path("bitacora/", include("auditoria.urls")),         # Daniel
]

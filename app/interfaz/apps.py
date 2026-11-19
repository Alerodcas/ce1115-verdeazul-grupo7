from django.apps import AppConfig


class InterfazConfig(AppConfig):
    """Interfaz web: plantillas, estáticos y vistas delgadas.

    Aquí no vive ninguna regla de negocio ni de autorización. Toda acción y todo
    listado lo hace el navegador contra la API existente (`/api/`,
    `/certificados/`, `/bitacora/`), así que el PEP sigue siendo el único camino.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "interfaz"

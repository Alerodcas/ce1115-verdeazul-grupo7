import os


def version(request):
    """La versión en ejecución, para el pie de cada pantalla: una captura prueba qué build era."""
    return {"version_app": os.environ.get("APP_VERSION", "dev")}

"""Vistas de infraestructura: salud, versión y portada.

Nada de negocio vive aquí. Las entidades (Finca, Medición, Certificado...)
las implementa Daniel en la app `negocio`.
"""

import os

from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache


@never_cache
def healthz(request):
    """Sonda de vida. Cloud Run y el startupProbe de Caddy la consultan.

    No toca la base de datos a propósito: si Neon está dormido, la instancia
    igual debe reportarse viva para no entrar en un ciclo de reinicios.
    """
    return JsonResponse({"status": "ok"})


@never_cache
def readyz(request):
    """Sonda de disponibilidad: sí comprueba la base de datos."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        base = "ok"
        codigo = 200
    except Exception:
        base = "sin conexion"
        codigo = 503
    return JsonResponse({"status": base, "version": os.environ.get("APP_VERSION", "dev")},
                        status=codigo)


def index(request):
    """Portada. Interfaz sobria, como permite el enunciado."""
    return render(request, "core/index.html", {"version": os.environ.get("APP_VERSION", "dev")})

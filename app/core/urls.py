from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    # Rutas públicas. NO pueden terminar en «z»: Cloud Run reserva algunas de
    # esas rutas (/healthz, /readyz, /livez, igual que Kubernetes) y su front
    # end las responde con un 404 propio ANTES de que la petición llegue al
    # contenedor. Se descubrió desplegando: /healthz devolvía el 404 de Google.
    path("health", views.healthz, name="health"),
    path("ready", views.readyz, name="ready"),
    # Se mantienen los nombres viejos para el entorno local y para cualquier
    # sonda que hable directo con el contenedor, donde sí funcionan.
    path("healthz", views.healthz, name="healthz"),
    path("readyz", views.readyz, name="readyz"),
]

"""Configuración de Gunicorn.

Escucha en loopback a propósito: el único cliente es Caddy, que corre como
contenedor de ingreso en la misma instancia de Cloud Run. Nada fuera de la
instancia puede hablarle a la aplicación directamente.
"""

import os

# Por omisión, loopback. Si la sonda de arranque de Cloud Run no alcanza el
# contenedor, se cambia con GUNICORN_BIND=0.0.0.0:8000 en service.yaml: dentro
# de una instancia de Cloud Run solo el puerto del contenedor de ingreso sale a
# internet, así que el puerto 8000 sigue siendo privado en ambos casos.
bind = os.environ.get("GUNICORN_BIND", f"127.0.0.1:{os.environ.get('APP_PORT', '8000')}")

# Cloud Run da 1 vCPU por omisión. Pocos trabajadores y varios hilos rinden
# mejor que muchos procesos, y consumen menos memoria de la capa gratuita.
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"

timeout = 60
graceful_timeout = 30
keepalive = 5

# Reciclar trabajadores limita el daño de una fuga de memoria y de un estado
# corrupto que sobreviva a una petición.
max_requests = 500
max_requests_jitter = 50

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# No se registra la cadena de consulta: puede traer identificadores del negocio.
access_log_format = '%(h)s "%(m)s %(U)s" %(s)s %(b)s %(D)sus'

forwarded_allow_ips = "127.0.0.1"

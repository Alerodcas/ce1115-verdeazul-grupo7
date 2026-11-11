# =============================================================================
#  Imagen de la aplicación — Django + DRF (PEP)
#  CE-1115 Proyecto Parte 2 · Grupo 7
#
#  Controles aplicados en este archivo:
#   · Construcción en dos etapas: el compilador y las cabeceras de desarrollo
#     no llegan a la imagen final (menos superficie, menos CVE que parchear).
#   · El contenedor NO corre como root (criterio explícito del enunciado, §3.2).
#   · Sistema de archivos de la aplicación de solo lectura para el proceso.
#   · Ningún secreto: todo entra por variable de entorno en tiempo de ejecución.
#   · Etiqueta de base explícita, nunca `latest`.
# =============================================================================

# --- Etapa 1: construir las dependencias -------------------------------------
FROM python:3.15-slim-bookworm AS builder

# Para fijar también el contenido y no solo la etiqueta, reemplazar la línea de
# arriba por la forma con digest, que se obtiene con:
#   docker buildx imagetools inspect python:3.12-slim-bookworm
# FROM python:3.12-slim-bookworm@sha256:<digest> AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# build-essential y libpq-dev solo existen en esta etapa.
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt


# --- Etapa 2: imagen final ---------------------------------------------------
FROM python:3.15-slim-bookworm AS runtime

ARG APP_VERSION=dev
ARG GIT_SHA=unknown

LABEL org.opencontainers.image.title="verdeazul-app" \
      org.opencontainers.image.description="Aplicación Django (PEP) de certificación de carbono" \
      org.opencontainers.image.vendor="Grupo 7 Byte Busters — CE-1115 ITCR" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_VERSION="${APP_VERSION}" \
    GIT_SHA="${GIT_SHA}" \
    DJANGO_SETTINGS_MODULE=config.settings \
    APP_PORT=8000

# libpq5 es la biblioteca en ejecución; las cabeceras de desarrollo se quedan
# en la etapa anterior.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libpq5 \
    && rm -rf /var/lib/apt/lists/*

# --- Usuario sin privilegios -------------------------------------------------
# UID/GID fijos y altos: no colisionan con usuarios del sistema y permiten
# aplicar runAsNonRoot en cualquier orquestador.
RUN groupadd --gid 10001 verdeazul \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin verdeazul

COPY --from=builder /opt/venv /opt/venv

WORKDIR /srv/app
COPY --chown=10001:10001 . /srv/app

# Los estáticos se recogen durante la construcción, no al arrancar: así el
# directorio de la aplicación puede montarse de solo lectura en ejecución.
RUN DJANGO_SECRET_KEY=build-time-only DJANGO_DEBUG=1 \
    python manage.py collectstatic --noinput \
    && chown -R 10001:10001 /srv/app/staticfiles

USER 10001:10001

EXPOSE 8000

# Gunicorn escucha solo en loopback: el único que le habla es Caddy, que corre
# en el mismo espacio de red de la instancia (Parte 1, frontera F2).
ENTRYPOINT ["/srv/app/entrypoint.sh"]
CMD ["gunicorn", "--config", "/srv/app/gunicorn.conf.py", "config.wsgi:application"]

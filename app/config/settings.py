"""
Configuración de Django — Verdeazul Carbono S.A.
CE-1115 Proyecto Parte 2 · Grupo 7 (Byte Busters)

Principio que rige este archivo: NINGÚN secreto vive aquí.
Todo lo sensible entra por variable de entorno, inyectada por Cloud Run
desde Secret Manager (ver deploy/service.yaml). En local entra por .env,
que está en .gitignore.

Responsable del archivo: Alejandra (infraestructura).
Los compañeros agregan sus apps en INSTALLED_APPS sin tocar el bloque de
seguridad de más abajo.
"""

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    """Lee una variable de entorno. Falla al arrancar si falta una obligatoria.

    Fallar al arrancar es deliberado: es preferible que el contenedor no
    levante a que levante con una clave por omisión.
    """
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(
            f"Falta la variable de entorno obligatoria {name}. "
            "En Cloud Run se inyecta desde Secret Manager; en local, desde .env"
        )
    return value or ""


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Entorno
# ---------------------------------------------------------------------------
DEBUG = env_bool("DJANGO_DEBUG", False)

# En producción la clave viene de Secret Manager. En desarrollo se permite una
# clave de juguete para que el contenedor arranque sin configurar nada.
SECRET_KEY = env("DJANGO_SECRET_KEY", required=not DEBUG) or "dev-only-insecure-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Cloud Run expone el servicio en https://<servicio>-<hash>.<region>.run.app
# Esa URL completa (con esquema) va aquí para que funcione el token CSRF.
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# ---------------------------------------------------------------------------
# Aplicaciones
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    # --- apps del proyecto ---
    "core",  # salud, base, plantillas comunes (Alejandra)
    "authz",  # PEP: cliente del motor de decisión OPA (Kevin)
    # "auditoria",   # bitácora de 7 capas (Daniel) — agregar cuando exista
    # "negocio",     # Finca, Período, Medición, Enmienda, Certificado (Daniel)
    # "certificados" # emisión y verificación firmada (Luis)
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Base de datos — Neon PostgreSQL
# ---------------------------------------------------------------------------
# DATABASE_URL llega desde Secret Manager. Formato de Neon:
#   postgresql://USUARIO:CLAVE@ep-xxxx-pooler.REGION.aws.neon.tech/DB?sslmode=require
# sslmode=require obliga a que la conexión viaje cifrada (Parte 1, frontera F4).
DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", "sqlite:///" + str(BASE_DIR / "dev.sqlite3")),
        conn_max_age=0,  # Cloud Run escala a cero: no conviene mantener conexiones
        ssl_require=not DEBUG,
    )
}

# ---------------------------------------------------------------------------
# Contraseñas — Argon2id (Parte 1, "Almacenamiento de credenciales")
# ---------------------------------------------------------------------------
# El orden importa: el primero es el que se usa para hashear contraseñas nuevas.
# Los demás quedan solo para verificar hashes viejos y re-hashear al entrar.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},  # Informe de políticas de la Parte 1
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Sesión (Parte 1, tabla "Gestión de sesión")
# ---------------------------------------------------------------------------
SESSION_ENGINE = "django.contrib.sessions.backends.db"  # sesión de servidor, revocable
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
# Inactividad: 15 min para roles críticos. Django aplica un solo valor global;
# el afinado por rol lo hace el middleware de sesión del equipo (pendiente).
SESSION_COOKIE_AGE = 15 * 60
SESSION_SAVE_EVERY_REQUEST = True  # renueva por actividad, no por tiempo absoluto

CSRF_COOKIE_HTTPONLY = False  # el token debe poder leerse desde el formulario
CSRF_COOKIE_SAMESITE = "Lax"

# ---------------------------------------------------------------------------
# Endurecimiento HTTP
# ---------------------------------------------------------------------------
# Cloud Run termina TLS en el front end de Google y pasa X-Forwarded-Proto.
# Caddy (contenedor de ingreso) reenvía esa cabecera tal cual.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Prefijo __Host-: el navegador solo acepta la cookie si viene por HTTPS,
    # con Path=/ y sin atributo Domain. Exige SECURE=True, por eso va aquí.
    SESSION_COOKIE_NAME = "__Host-sid"
    CSRF_COOKIE_NAME = "__Host-csrftoken"
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Límite de tamaño de la petición. Caddy corta antes (ver caddy/Caddyfile),
# esto es la segunda línea de defensa dentro de la aplicación.
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024  # 2 MiB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200

# ---------------------------------------------------------------------------
# Motor de decisión (PDP) — OPA como sidecar, solo por loopback
# ---------------------------------------------------------------------------
# Parte 1, frontera F3: el PDP no se expone a la red.
OPA_URL = env("OPA_URL", "http://127.0.0.1:8181")
OPA_DECISION_PATH = env("OPA_DECISION_PATH", "verdeazul/authz/decision")
OPA_TIMEOUT_SECONDS = float(env("OPA_TIMEOUT_SECONDS", "2"))
# Si el motor no responde, se deniega (falla cerrada).
OPA_FAIL_CLOSED = True

# ---------------------------------------------------------------------------
# REST Framework — denegar por omisión
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Nada es público salvo que una vista lo diga explícitamente.
    "DEFAULT_PERMISSION_CLASSES": [
        "authz.permissions.DenyAll",
    ],
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

# ---------------------------------------------------------------------------
# Estáticos
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ---------------------------------------------------------------------------
# Registro de la aplicación (NO es la bitácora de auditoría)
# ---------------------------------------------------------------------------
# La bitácora de auditoría es otra cosa y la implementa Daniel (app `auditoria`).
# Esto es solo el log operativo del proceso, que Cloud Run recoge de stdout.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(levelname)s %(asctime)s %(name)s %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "INFO")},
}

LANGUAGE_CODE = "es-cr"
TIME_ZONE = "UTC"  # la bitácora exige UTC (Parte 1, campo ts_utc)
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

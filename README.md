# Verdeazul Carbono S.A. — Sistema de certificación

**CE-1115 Seguridad de la Información · Proyecto Parte 2 · Grupo 7 (Byte Busters) · ITCR, II Semestre 2026**

Implementación y despliegue del sistema diseñado en la Parte 1: control de acceso
híbrido RBAC2 + ABAC, bitácora de auditoría y emisión de certificados de carbono
firmados digitalmente.

- **URL pública:** _(se completa tras el primer despliegue)_
- **Versión desplegada:** _(se completa tras el primer despliegue)_

---

## 1. Qué corre y dónde

El servicio es **una sola instancia de Cloud Run con tres contenedores** que
comparten la red local de la instancia. Reproduce las zonas del diseño de la
Parte 1 con las piezas que exige el enunciado de la Parte 2.

```
                   ┌─────────────────────────────────────────────┐
  internet         │          instancia de Cloud Run             │
     │             │                                             │
     │  HTTPS      │   ┌──────────┐  loopback  ┌──────────────┐  │
     └────────────►│   │  caddy   │───────────►│     app      │  │
   front end de    │   │  :8080   │            │ Django + DRF │  │
   Google (TLS)    │   │ Zona 1   │            │  (PEP) :8000 │  │
                   │   └──────────┘            └───────┬──────┘  │
                   │                                   │loopback │
                   │                           ┌───────▼──────┐  │
                   │                           │     opa      │  │
                   │                           │  (PDP) :8181 │  │
                   │                           └──────────────┘  │
                   └───────────────────┬─────────────────────────┘
                                       │ TLS
                        ┌──────────────┴──────────────┐
                        ▼                             ▼
               ┌──────────────────┐        ┌────────────────────┐
               │ Neon PostgreSQL  │        │  Secret Manager    │
               │ (datos+bitácora) │        │ (3 secretos)       │
               └──────────────────┘        └────────────────────┘
```

| Contenedor | Imagen | Puerto | Qué hace |
|---|---|---|---|
| `caddy` | `…/verdeazul/caddy` | 8080 (ingreso) | Único expuesto. Límite de tasa y de tamaño, métodos permitidos, cabeceras de seguridad. |
| `app` | `…/verdeazul/app` | 8000 (loopback) | Django + DRF. Autenticación, sesión, validación, punto de aplicación de la política (PEP). |
| `opa` | `…/verdeazul/opa` | 8181 (loopback) | Motor de decisión (PDP) con las reglas de la matriz en Rego. No alcanzable desde internet. |

Detalle de componentes, fronteras de confianza y desviaciones respecto a la
Parte 1: [`docs/ARQUITECTURA-DESPLEGADA.md`](docs/ARQUITECTURA-DESPLEGADA.md) y
[`docs/DESVIACIONES.md`](docs/DESVIACIONES.md).

---

## 2. Estructura del repositorio

```
app/          aplicación Django (PEP) + Dockerfile
  config/     settings, urls, wsgi
  core/       salud, versión, portada
  authz/      cliente del PDP y clases de permiso
caddy/        Caddyfile + Dockerfile del proxy de ingreso
opa/          políticas en Rego + Dockerfile del motor de decisión
deploy/       service.yaml de Cloud Run y los guiones de despliegue
docs/         arquitectura desplegada, guía de despliegue, desviaciones
.github/      integración continua y Dependabot
compose.yaml  entorno local con la misma topología
```

---

## 3. Desarrollo local

```bash
cp .env.example .env
docker compose up --build
# http://localhost:8080
```

Reproduce la topología de la nube: solo el puerto de Caddy sale al anfitrión; la
aplicación y el motor de decisión quedan detrás. La base de datos local es un
contenedor de PostgreSQL 17, no Neon.

Sin Docker:

```bash
cd app
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example ../.env       # y ajustar DATABASE_URL a sqlite o a Neon
python manage.py migrate
python manage.py runserver
```

---

## 4. Despliegue

Guía completa, paso a paso, incluida la creación de las cuentas:
[`docs/GUIA-DESPLIEGUE.md`](docs/GUIA-DESPLIEGUE.md).

Resumen, una vez que el proyecto de Google Cloud y el de Neon existen:

```bash
cp deploy/config.env.example deploy/config.env   # completar identificadores
bash deploy/setup-gcp.sh                         # APIs, registro, cuentas, secretos  (una vez)
# ... cargar el valor real de cada secreto (ver la guía) ...
bash deploy/build-push.sh v1.0.0                 # construye y publica las 3 imágenes
bash deploy/migrate.sh   v1.0.0                  # aplica migraciones contra Neon
bash deploy/deploy.sh    v1.0.0                  # despliega el servicio
```

`deploy/config.env` está en `.gitignore` y **solo contiene identificadores**, no
secretos.

### Por qué el despliegue va por YAML y no por `gcloud run deploy`

Los servicios con varios contenedores no se pueden describir con banderas de
línea de comandos. `deploy/deploy.sh` sustituye las variables de
`deploy/service.yaml` y llama a `gcloud run services replace`.

---

## 5. Versionado de imágenes

Cada publicación produce **dos etiquetas sobre la misma imagen**:

| Etiqueta | Para qué sirve |
|---|---|
| `vMAYOR.MENOR.PARCHE` | Es la que se despliega y la que se cita en el informe. |
| `sha-<commit corto>` | Dice exactamente qué código corresponde a esa imagen. |

**No se publica `latest`.** Una etiqueta que se mueve no permite responder las
dos preguntas que importan cuando aparece una vulnerabilidad: *¿qué versión está
corriendo?* y *¿a cuál volvemos?*

### Versiones publicadas

| Versión | Commit | Fecha | Qué cambió |
|---|---|---|---|
| _(pendiente)_ | | | |

> Mantener esta tabla al día: el enunciado pide que el README traiga las
> etiquetas de versión publicadas (Entregable 2).

---

## 6. Secretos

Tres secretos, todos en Secret Manager, inyectados como variables de entorno por
Cloud Run. **Ninguno aparece en el código, en el `Dockerfile`, en las imágenes ni
en este repositorio.**

| Secreto | Contenido | Quién lo lee |
|---|---|---|
| `verdeazul-django-secret-key` | Clave de firma de sesiones y tokens de Django | contenedor `app` |
| `verdeazul-database-url` | Cadena de conexión a Neon, con `sslmode=require` | contenedor `app` |
| `verdeazul-cert-signing-key` | Clave privada de firma de certificados | contenedor `app` |

La cuenta de servicio con la que **corre** el servicio puede leerlos.
La cuenta con la que **se despliega** no puede: quien tiene acceso al código no
tiene acceso a producción.

El repositorio se escanea con `gitleaks` en cada integración (`.gitleaks.toml`).
Si un secreto entra al historial se considera comprometido y se rota; borrar el
commit no basta.

Responsable: **Eder**. Detalle en la sección 5.1.3 del informe.

---

## 7. Integración continua

`.github/workflows/ci.yml` corre en cada push y cada pull request:

| Comprobación | Herramienta | Qué detecta |
|---|---|---|
| Secretos en el historial | gitleaks | Credenciales confirmadas al repositorio |
| Lint | ruff | Errores y código muerto |
| Análisis estático | bandit | Patrones inseguros en Python |
| Dependencias | pip-audit | Vulnerabilidades conocidas |
| Configuración de Django | `check --deploy` | `DEBUG`, cookies sin `Secure`, HSTS |
| Política de autorización | `opa check`, `opa test` | Reglas que no compilan o que conceden de más |
| Contenedores | comprobación propia | Que ninguna imagen corra como root |
| Imágenes | Trivy | CVE en las capas base |

Dependabot vigila Python, las imágenes base y las propias acciones de GitHub
(`.github/dependabot.yml`).

---

## 8. Reparto del trabajo

| Integrante | Responsabilidad | Dónde vive en el repositorio |
|---|---|---|
| Alejandra Rodríguez Castro | Infraestructura, despliegue y red | `deploy/`, `caddy/`, los tres `Dockerfile`, `.github/`, `compose.yaml` |
| Kevin Chinchilla Rodríguez | Motor de autorización (RBAC2 + ABAC) | `opa/policies/`, `app/authz/` |
| Eder Vega Suazo | Gestión de secretos y seguridad heredada | Secret Manager, Dependabot, secciones 5.1.3 y 5.1.4 |
| Luis Alexis Alvarado Barrantes | Certificación digital y políticas de cuentas | app `certificados` (pendiente), sección 5.1.5 |
| Daniel Cob Beirute | Auditoría, trazabilidad y datos | apps `negocio` y `auditoria` (pendientes), consolidación del informe |

La defensa es individual: cada quien responde por el sistema completo.

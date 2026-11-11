# Guía de despliegue, paso a paso

**CE-1115 Proyecto Parte 2 · Grupo 7 · Responsable: Alejandra**

Esta guía va desde «no hay nada» hasta «el sistema abre desde internet por
HTTPS». Los pasos marcados con 🔑 necesitan una cuenta y hay que hacerlos a
mano; los demás los hace un guion del repositorio.

> **El consejo del enunciado (§9) en serio:** desplegar algo mínimo la primera
> semana, aunque solo diga «hola», y después agregarle funcionalidad. Dejar el
> despliegue para el final es la forma más común de no llegar. Los pasos 1 a 7
> se pueden completar hoy, con el esqueleto que ya está en el repositorio.

---

## Antes de empezar

Hace falta tener instalado:

- **Git** y una cuenta de GitHub.
- **Google Cloud CLI** (`gcloud`) — <https://cloud.google.com/sdk/docs/install>.
  En Windows, el instalador `.exe`; al terminar, abrir una terminal nueva.
- **Docker Desktop** *(opcional)*. Solo para probar en local. Las imágenes de la
  nube las construye Cloud Build, así que no es obligatorio.

Comprobar:

```bash
gcloud --version
git --version
```

---

## Paso 1 🔑 — Crear el proyecto de Google Cloud

1. Entrar a <https://console.cloud.google.com> con la cuenta institucional o
   personal.
2. Arriba, en el selector de proyecto → **Nuevo proyecto**.
   - Nombre: `verdeazul-ce1115`
   - Anotar el **ID del proyecto** que queda asignado (puede llevar números al
     final, p. ej. `verdeazul-ce1115-482301`). **Ese ID es el que se usa en
     todo lo demás, no el nombre.**
3. Google pide una tarjeta para activar la facturación. La capa gratuita de
   Cloud Run cubre este proyecto de sobra, pero **si el curso no permite
   registrar tarjeta, avisar al profesor antes de registrarse** (§8 del
   enunciado: «si algún servicio les pide tarjeta, avisen antes»).

Autenticar la línea de comandos:

```bash
gcloud auth login
gcloud config set project TU-ID-DE-PROYECTO
```

> **Consumo.** Mantener el servicio con `maxScale: 2` (ya está en
> `deploy/service.yaml`) y no correr pruebas de carga. Conviene además poner una
> alerta de presupuesto en **Facturación → Presupuestos y alertas** por un monto
> simbólico (1 USD), para enterarse si algo se dispara.

---

## Paso 2 🔑 — Crear la base de datos en Neon

1. Entrar a <https://neon.tech> y crear cuenta (el plan gratuito no pide
   tarjeta).
2. **Create project**:
   - Nombre: `verdeazul`
   - Versión de PostgreSQL: **17** (es la que fija el diseño de la Parte 1).
   - Región: la misma zona que Cloud Run, para que la latencia no moleste.
     Si Cloud Run va en `us-central1`, elegir `AWS us-east-1` o la más cercana
     que ofrezca Neon.
3. Copiar la **cadena de conexión**. Se ve así:

   ```
   postgresql://verdeazul_owner:CLAVE@ep-algo-pooler.us-east-1.aws.neon.tech/verdeazul?sslmode=require
   ```

   Usar la variante **pooled** (la que dice `-pooler`): Cloud Run abre y cierra
   instancias, y el agrupador evita agotar las conexiones.

   **Guardarla en un lugar temporal y no pegarla en ningún archivo del
   repositorio.** En el paso 5 se carga a Secret Manager y se borra de donde se
   haya copiado.

4. Mientras se está en la consola de Neon, anotar para la sección 5.1.4 del
   informe (la que escribe Eder): qué opciones de seguridad ofrece el plan y
   cuáles quedaron activas. Ver `docs/ARQUITECTURA-DESPLEGADA.md`, sección
   «Seguridad heredada».

---

## Paso 3 🔑 — Crear el repositorio en GitHub

1. GitHub → **New repository** → nombre `ce1115-verdeazul-grupo7`, **privado**.
2. Subir el contenido de esta carpeta:

   ```bash
   cd ce1115-verdeazul-grupo7
   git init -b main
   git add .
   git commit -m "Esqueleto del sistema: contenedores, despliegue y CI"
   git remote add origin https://github.com/TU-USUARIO/ce1115-verdeazul-grupo7.git
   git push -u origin main
   ```

3. Agregar a los cuatro compañeros en **Settings → Collaborators**.
4. **Settings → Code security** → activar:
   - *Dependabot alerts*
   - *Dependabot security updates*
   - *Secret scanning* y *Push protection* (si el repositorio es privado, puede
     requerir la opción gratuita para cuentas educativas; si no aparece, anotarlo
     y seguir: `gitleaks` cubre lo mismo desde CI).

   Esto es responsabilidad de **Eder**, pero conviene dejarlo activo desde el
   primer día: si Dependabot no levanta ninguna alerta durante el proyecto, no
   hay qué documentar.

---

## Paso 4 — Preparar Google Cloud (automático)

```bash
cp deploy/config.env.example deploy/config.env
```

Editar `deploy/config.env` con el ID real del proyecto. Las dos líneas de las
cuentas de servicio tienen que llevar ese mismo ID:

```ini
PROJECT_ID=verdeazul-ce1115-482301
REGION=us-central1
SERVICE_NAME=verdeazul
AR_REPO=verdeazul
RUNTIME_SA=verdeazul-run@verdeazul-ce1115-482301.iam.gserviceaccount.com
DEPLOY_SA=verdeazul-deploy@verdeazul-ce1115-482301.iam.gserviceaccount.com
PUBLIC_HOST=
```

Y correr:

```bash
bash deploy/setup-gcp.sh
```

Deja listo, sin intervención: las APIs, el repositorio de Artifact Registry, las
dos cuentas de servicio con permisos separados y los tres secretos **vacíos**.

> En Windows, correr esto desde **Git Bash** o desde **WSL**, no desde PowerShell.
> Alternativa sin instalar nada: abrir **Cloud Shell** en la consola de Google
> (el icono `>_` arriba a la derecha), clonar ahí el repositorio y correr el
> guion. Cloud Shell ya trae `gcloud`, `git` y Docker.

---

## Paso 5 🔑 — Cargar el valor real de cada secreto

Tres comandos. Cada uno manda el valor por la entrada estándar para que **no
quede en el historial del intérprete de comandos**.

```bash
# 1. Clave de firma de Django — se genera, nadie la escribe
python -c "import secrets; print(secrets.token_urlsafe(64), end='')" \
  | gcloud secrets versions add verdeazul-django-secret-key --data-file=-

# 2. Cadena de conexión a Neon (pegar la del paso 2, entre comillas simples)
printf '%s' 'postgresql://USUARIO:CLAVE@ep-xxxx-pooler.REGION.aws.neon.tech/verdeazul?sslmode=require' \
  | gcloud secrets versions add verdeazul-database-url --data-file=-

# 3. Clave privada de firma de certificados — la genera Luis.
#    Provisionalmente, para que el servicio arranque:
printf '%s' 'pendiente' \
  | gcloud secrets versions add verdeazul-cert-signing-key --data-file=-
```

Comprobar que quedaron (muestra las versiones, **no** los valores):

```bash
gcloud secrets versions list verdeazul-database-url
```

Después de esto, **borrar la cadena de conexión** del bloc de notas, del chat del
grupo y de donde se haya copiado. Si pasó por un chat, se considera comprometida:
rotar la contraseña desde la consola de Neon y cargar una versión nueva del
secreto.

> **Captura para el informe (sección 5.1.3):** la pantalla de Secret Manager con
> los tres secretos listados y sus versiones. Que se vean los nombres y las
> fechas, nunca un valor.

---

## Paso 6 — Construir y publicar las imágenes

```bash
bash deploy/build-push.sh v1.0.0
```

Construye las tres imágenes en Cloud Build (no hace falta Docker local) y las
publica en Artifact Registry con dos etiquetas: `v1.0.0` y `sha-<commit>`.

Al final imprime los *digests*. **Copiarlos al README**, en la tabla «Versiones
publicadas»: es la evidencia de versionado explícito que pide el enunciado.

> Si la construcción de `caddy` falla porque el módulo de límite de tasa no
> compila, hay un plan B escrito en `caddy/Dockerfile`: usar la imagen oficial
> `caddy:2.9-alpine` y quitar el bloque `rate_limit` del `Caddyfile`. El sistema
> queda funcionando y se anota como desviación.

---

## Paso 7 — Migrar la base de datos y desplegar

```bash
bash deploy/migrate.sh v1.0.0    # crea las tablas en Neon
bash deploy/deploy.sh   v1.0.0   # despliega el servicio
```

El primer despliegue imprime la URL pública. **Anotarla en `deploy/config.env`**
(sin `https://`) y volver a desplegar, para que `ALLOWED_HOSTS` quede fijado al
dominio exacto en vez del comodín:

```ini
PUBLIC_HOST=verdeazul-abc123-uc.a.run.app
```

```bash
bash deploy/deploy.sh v1.0.0
```

Comprobar desde **una red distinta** a la de la casa (datos del celular, por
ejemplo). El enunciado lo pide explícitamente: «prueben desde una red distinta a
la suya antes de presentar».

```bash
curl -sI https://verdeazul-abc123-uc.a.run.app/healthz
# HTTP/2 200

curl -sI http://verdeazul-abc123-uc.a.run.app/healthz
# debe redirigir a https
```

> **Captura para el informe (criterio de despliegue, 16 pts):** el navegador con
> el candado, la URL `*.run.app` visible, y el sistema respondiendo. Conviene
> también una captura de la consola de Cloud Run mostrando los **tres
> contenedores** de la revisión, porque esa es la evidencia de que la
> arquitectura diseñada existe de verdad y no es solo un dibujo.

---

## Paso 8 — Actualizar después de cada cambio

```bash
git commit -am "..." && git push
bash deploy/build-push.sh v1.1.0
bash deploy/migrate.sh   v1.1.0     # solo si hubo migraciones nuevas
bash deploy/deploy.sh    v1.1.0
```

Subir el número de versión siempre. Volver a desplegar la misma etiqueta con
código distinto rompe la trazabilidad, que es justo lo que el enunciado evalúa.

---

## Si algo falla

| Síntoma | Causa más probable | Qué hacer |
|---|---|---|
| `Revision ... is not ready` y el registro no dice nada | El contenedor `app` no pasó la sonda de arranque | Agregar `GUNICORN_BIND=0.0.0.0:8000` al bloque `env` de `app` en `deploy/service.yaml` y volver a desplegar |
| `DisallowedHost` en los registros | `PUBLIC_HOST` no coincide con la URL real | Corregirlo en `deploy/config.env` y volver a desplegar |
| `CSRF verification failed` al enviar un formulario | Falta el origen en `DJANGO_CSRF_TRUSTED_ORIGINS` | Se arma solo desde `PUBLIC_HOST`; verificar que lleve `https://` |
| `could not connect to server` | La cadena de Neon está mal o el proyecto está suspendido | Revisar el secreto; comprobar en la consola de Neon que el *compute* no esté suspendido por límite mensual |
| `PermissionDenied` al leer un secreto | Falta el permiso a la cuenta de ejecución | Volver a correr `bash deploy/setup-gcp.sh` (es idempotente) |
| `Permission denied` al desplegar | La cuenta de `gcloud` no es dueña del proyecto | `gcloud auth list` y `gcloud config set account ...` |

Ver los registros:

```bash
gcloud run services logs read verdeazul --region us-central1 --limit 100
```

---

## Qué queda fuera del alcance de esta guía

- Las reglas de la matriz en Rego — **Kevin**.
- La emisión y verificación de certificados firmados — **Luis**.
- La bitácora de auditoría y los modelos de datos — **Daniel**.
- El análisis de seguridad heredada de Neon y Cloud Run — **Eder**.

#!/usr/bin/env bash
# =============================================================================
#  Preparación del proyecto de Google Cloud — se corre UNA SOLA VEZ
#  CE-1115 Proyecto Parte 2 · Grupo 7 · Responsable: Alejandra
#
#  Qué deja listo:
#    1. Las APIs que el proyecto necesita.
#    2. El repositorio de Artifact Registry donde viven las imágenes.
#    3. Dos cuentas de servicio con permisos mínimos y separados:
#         - verdeazul-run     : con la que CORRE el servicio
#         - verdeazul-deploy  : con la que CI construye y despliega
#    4. Los secretos en Secret Manager, con acceso solo para la cuenta de
#       ejecución.
#
#  Lo que NO hace, y hay que hacer a mano antes:
#    - crear el proyecto de Google Cloud
#    - crear el proyecto de Neon y copiar la cadena de conexión
#  Ver docs/GUIA-DESPLIEGUE.md.
#
#  Uso:  cp config.env.example config.env && nano config.env
#        bash deploy/setup-gcp.sh
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")"
# shellcheck source=/dev/null
source ./config.env

say() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

say "Proyecto activo: ${PROJECT_ID} (región ${REGION})"
gcloud config set project "${PROJECT_ID}" >/dev/null

# -----------------------------------------------------------------------------
say "1/6 Habilitando APIs"
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    cloudbuild.googleapis.com \
    iamcredentials.googleapis.com

# -----------------------------------------------------------------------------
say "2/6 Creando el repositorio de imágenes en Artifact Registry"
if ! gcloud artifacts repositories describe "${AR_REPO}" --location="${REGION}" >/dev/null 2>&1; then
    gcloud artifacts repositories create "${AR_REPO}" \
        --repository-format=docker \
        --location="${REGION}" \
        --description="Imagenes del sistema de certificacion de carbono (Grupo 7)"
else
    echo "    ya existía, no se toca"
fi

# -----------------------------------------------------------------------------
say "3/6 Creando las cuentas de servicio"
crear_sa() {
    local nombre="$1" descripcion="$2"
    if ! gcloud iam service-accounts describe "${nombre}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1; then
        gcloud iam service-accounts create "${nombre}" --display-name="${descripcion}"
    else
        echo "    ${nombre} ya existía"
    fi
}
crear_sa verdeazul-run    "Ejecucion del servicio Cloud Run"
crear_sa verdeazul-deploy "Construccion y despliegue desde CI"

# -----------------------------------------------------------------------------
say "4/6 Creando los secretos (con valores provisionales)"
# Importante: los valores reales se cargan después, uno por uno, con
#   printf '%s' "VALOR" | gcloud secrets versions add NOMBRE --data-file=-
# Se usa printf y no echo para no agregar un salto de línea al secreto, y se
# lee desde la entrada estándar para que el valor no quede en el historial del
# intérprete de comandos.
crear_secreto() {
    local nombre="$1"
    if ! gcloud secrets describe "${nombre}" >/dev/null 2>&1; then
        gcloud secrets create "${nombre}" --replication-policy=automatic
        echo "    creado ${nombre} — falta cargarle la versión con el valor real"
    else
        echo "    ${nombre} ya existía"
    fi
}
crear_secreto verdeazul-django-secret-key
crear_secreto verdeazul-database-url
crear_secreto verdeazul-cert-signing-key

# -----------------------------------------------------------------------------
say "5/6 Permisos mínimos"

# La cuenta de EJECUCIÓN solo puede LEER los secretos. No puede crearlos,
# borrarlos, ni listar otros. Si la aplicación se compromete, no puede
# escalar dentro del proyecto.
for secreto in verdeazul-django-secret-key verdeazul-database-url verdeazul-cert-signing-key; do
    gcloud secrets add-iam-policy-binding "${secreto}" \
        --member="serviceAccount:${RUNTIME_SA}" \
        --role="roles/secretmanager.secretAccessor" >/dev/null
done
echo "    ${RUNTIME_SA}: solo lectura de los 3 secretos"

# La cuenta de DESPLIEGUE puede publicar imágenes y actualizar el servicio,
# pero NO puede leer los secretos. Quien tiene acceso al código no tiene
# acceso a producción (Parte 1, regla 1 de gestión de secretos).
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${DEPLOY_SA}" \
    --role="roles/artifactregistry.writer" >/dev/null
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${DEPLOY_SA}" \
    --role="roles/run.developer" >/dev/null
# Necesario para que el despliegue pueda asignarle al servicio la cuenta de
# ejecución; es el permiso mínimo para eso, no es suplantación general.
gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_SA}" \
    --member="serviceAccount:${DEPLOY_SA}" \
    --role="roles/iam.serviceAccountUser" >/dev/null
echo "    ${DEPLOY_SA}: publicar imágenes y desplegar, SIN acceso a secretos"

# -----------------------------------------------------------------------------
say "6/6 Listo"
cat <<FIN

Siguientes pasos (docs/GUIA-DESPLIEGUE.md):

  1. Cargar el valor real de cada secreto:

       python -c "import secrets;print(secrets.token_urlsafe(64))" \\
         | tr -d '\\n' | gcloud secrets versions add verdeazul-django-secret-key --data-file=-

       printf '%s' 'postgresql://USUARIO:CLAVE@ep-xxxx-pooler.${REGION}.aws.neon.tech/verdeazul?sslmode=require' \\
         | gcloud secrets versions add verdeazul-database-url --data-file=-

  2. Construir y publicar las imágenes:   bash deploy/build-push.sh v1.0.0
  3. Desplegar:                           bash deploy/deploy.sh v1.0.0

FIN

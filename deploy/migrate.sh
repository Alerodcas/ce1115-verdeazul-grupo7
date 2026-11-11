#!/usr/bin/env bash
# =============================================================================
#  Aplica las migraciones de Django contra Neon
#  CE-1115 Proyecto Parte 2 · Grupo 7
#
#  Se corre como un Job de Cloud Run, no al arrancar el servicio: si Cloud Run
#  levanta dos instancias a la vez, dos `migrate` simultáneos se estorban.
#
#  Usa la MISMA imagen de la aplicación y los MISMOS secretos, así que la
#  cadena de conexión tampoco pasa por la máquina de nadie.
#
#  Uso:  bash deploy/migrate.sh v1.0.0
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=/dev/null
source ./deploy/config.env

VERSION="${1:-}"
[[ -n "${VERSION}" ]] || { echo "Uso: bash deploy/migrate.sh v1.0.0" >&2; exit 1; }

REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"
JOB="${SERVICE_NAME}-migrate"

ACCION=create
gcloud run jobs describe "${JOB}" --project="${PROJECT_ID}" --region="${REGION}" >/dev/null 2>&1 \
    && ACCION=update

gcloud run jobs "${ACCION}" "${JOB}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --image="${REGISTRY}/app:${VERSION}" \
    --service-account="${RUNTIME_SA}" \
    --max-retries=1 \
    --task-timeout=10m \
    --set-env-vars="DJANGO_DEBUG=False,DJANGO_ALLOWED_HOSTS=${PUBLIC_HOST:-.run.app}" \
    --set-secrets="DJANGO_SECRET_KEY=verdeazul-django-secret-key:latest,DATABASE_URL=verdeazul-database-url:latest" \
    --command="python" \
    --args="manage.py,migrate,--noinput" \
    --quiet

echo "Ejecutando migraciones..."
gcloud run jobs execute "${JOB}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --wait

echo "Migraciones aplicadas."

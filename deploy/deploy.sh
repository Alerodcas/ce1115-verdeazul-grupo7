#!/usr/bin/env bash
# =============================================================================
#  Despliega el servicio de tres contenedores en Cloud Run
#  CE-1115 Proyecto Parte 2 · Grupo 7 · Responsable: Alejandra
#
#  Uso:  bash deploy/deploy.sh v1.0.0
#
#  Toma deploy/service.yaml, sustituye las variables y llama a
#  `gcloud run services replace`. Los servicios con varios contenedores no se
#  pueden desplegar con banderas de `gcloud run deploy`: hace falta el YAML.
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=/dev/null
source ./deploy/config.env

VERSION="${1:-}"
if [[ ! "${VERSION}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Uso: bash deploy/deploy.sh vMAYOR.MENOR.PARCHE   (ejemplo: v1.0.0)" >&2
    exit 1
fi

export REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"
export IMAGE_TAG="${VERSION}"
export SERVICE_NAME REGION RUNTIME_SA
# Sufijo de revisión: versión + marca de tiempo, en minúsculas y con guiones,
# que es lo único que acepta Cloud Run en el nombre de una revisión.
export REVISION_SUFFIX="${VERSION//./-}-$(date -u +%H%M%S)"

# En el PRIMER despliegue todavía no se conoce la URL pública, y ALLOWED_HOSTS
# no puede quedar vacío. Se usa un comodín de *.run.app y después se ajusta
# a la URL exacta. Django acepta el comodín de subdominio con punto inicial.
if [[ -z "${PUBLIC_HOST:-}" ]]; then
    echo "AVISO: PUBLIC_HOST está vacío en deploy/config.env."
    echo "       Se despliega con '.run.app' y al terminar se imprime la URL real"
    echo "       para que la anotes y vuelvas a desplegar."
    export PUBLIC_HOST=".run.app"
fi

PLANTILLA=./deploy/service.yaml
GENERADO="$(mktemp -t verdeazul-service-XXXXXX.yaml)"
trap 'rm -f "${GENERADO}"' EXIT

# Sustitucion de variables. Se prefiere envsubst, pero no existe en todos los
# entornos (Git Bash en Windows, por ejemplo), asi que hay respaldo en Python.
VARIABLES='${SERVICE_NAME} ${REGION} ${REVISION_SUFFIX} ${RUNTIME_SA} ${REGISTRY} ${IMAGE_TAG} ${PUBLIC_HOST}'
if command -v envsubst >/dev/null 2>&1; then
    envsubst "${VARIABLES}" < "${PLANTILLA}" > "${GENERADO}"
else
    echo "envsubst no esta disponible; se usa Python para sustituir las variables."
    python3 -c '
import os, re, sys
nombres = ["SERVICE_NAME","REGION","REVISION_SUFFIX","RUNTIME_SA","REGISTRY","IMAGE_TAG","PUBLIC_HOST"]
faltan = [n for n in nombres if os.environ.get(n) is None]
if faltan:
    sys.exit("faltan variables de entorno: " + ", ".join(faltan))
texto = open(sys.argv[1], encoding="utf-8").read()
texto = re.sub(r"\$\{(" + "|".join(nombres) + r")\}", lambda m: os.environ[m.group(1)], texto)
open(sys.argv[2], "w", encoding="utf-8").write(texto)
' "${PLANTILLA}" "${GENERADO}"
fi

# Si quedo alguna de las siete variables sin sustituir, el manifiesto es invalido:
# mejor parar aqui que desplegar una imagen con la etiqueta literal '${IMAGE_TAG}'.
# Se buscan los nombres exactos, no cualquier '${', porque los comentarios del
# propio YAML mencionan la sintaxis.
if grep -qE '\$\{(SERVICE_NAME|REGION|REVISION_SUFFIX|RUNTIME_SA|REGISTRY|IMAGE_TAG|PUBLIC_HOST)\}' "${GENERADO}"; then
    echo "ERROR: quedaron variables sin sustituir en el manifiesto:" >&2
    grep -nE '\$\{(SERVICE_NAME|REGION|REVISION_SUFFIX|RUNTIME_SA|REGISTRY|IMAGE_TAG|PUBLIC_HOST)\}' "${GENERADO}" >&2
    exit 1
fi

echo "=== Manifiesto que se va a aplicar ==="
grep -E 'image:|name:|serviceAccountName' "${GENERADO}"
echo

gcloud run services replace "${GENERADO}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --quiet

# El servicio debe ser alcanzable sin autenticación: el profesor abre la URL
# desde internet. El control de acceso vive DENTRO de la aplicación (el PEP),
# no en la capa de IAM de Cloud Run.
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --member="allUsers" \
    --role="roles/run.invoker" \
    --quiet >/dev/null

URL="$(gcloud run services describe "${SERVICE_NAME}" \
    --project="${PROJECT_ID}" --region="${REGION}" --format='value(status.url)')"

echo
echo "Desplegado: ${URL}"
echo
if [[ "${PUBLIC_HOST}" == ".run.app" ]]; then
    echo "ANOTAR en deploy/config.env:"
    echo "    PUBLIC_HOST=${URL#https://}"
    echo "y volver a correr este script para fijar ALLOWED_HOSTS a la URL exacta."
else
    echo "Comprobación rápida:"
    echo "    curl -sI ${URL}/healthz | head -1"
fi

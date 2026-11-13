#!/usr/bin/env bash
# =============================================================================
#  Construye y publica las tres imágenes en Artifact Registry
#  CE-1115 Proyecto Parte 2 · Grupo 7 · Responsable: Alejandra
#
#  Uso:  bash deploy/build-push.sh v1.0.0
#
#  Versionado (§3.2 del enunciado):
#    · Cada imagen lleva una etiqueta de versión explícita: v1.0.0, v1.1.0...
#    · Además lleva el hash corto del commit, para saber exactamente qué código
#      corresponde a esa imagen.
#    · NO se publica `latest`. Publicar solo `latest` cuesta la mitad del
#      criterio de contenedores.
#
#  Usa Cloud Build, así que NO hace falta tener Docker instalado en la máquina.
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=/dev/null
source ./deploy/config.env

VERSION="${1:-}"
if [[ ! "${VERSION}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Uso: bash deploy/build-push.sh vMAYOR.MENOR.PARCHE   (ejemplo: v1.0.0)" >&2
    exit 1
fi

GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
    echo "AVISO: hay cambios sin confirmar. La imagen ${VERSION} no va a corresponder"
    echo "       exactamente al commit ${GIT_SHA}. Confirmar antes de publicar."
    read -rp "       ¿Continuar de todos modos? [s/N] " respuesta
    [[ "${respuesta}" == "s" ]] || exit 1
fi

REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"

construir() {
    local componente="$1" contexto="$2"
    echo
    echo "=== ${componente} : ${VERSION} (${GIT_SHA}) ==="
    # --service-account: se construye con la identidad de despliegue, que tiene
    #   lo justo para construir y publicar, y ningún acceso a los secretos. Sin
    #   esta bandera, Cloud Build usa la cuenta por omisión de Compute Engine,
    #   que en los proyectos nuevos no tiene permisos y falla.
    # --default-buckets-behavior: con una identidad propia hay que mandar los
    #   registros a un bucket regional del propio proyecto.
    gcloud builds submit "${contexto}" \
        --project="${PROJECT_ID}" \
        --tag="${REGISTRY}/${componente}:${VERSION}" \
        --service-account="projects/${PROJECT_ID}/serviceAccounts/${DEPLOY_SA}" \
        --default-buckets-behavior=regional-user-owned-bucket \
        --quiet
    # Segunda etiqueta con el hash del commit, sobre la MISMA imagen.
    gcloud artifacts docker tags add \
        "${REGISTRY}/${componente}:${VERSION}" \
        "${REGISTRY}/${componente}:sha-${GIT_SHA}" --quiet
}

construir app   ./app
construir caddy ./caddy
construir opa   ./opa

echo
echo "Publicadas en ${REGISTRY} con las etiquetas ${VERSION} y sha-${GIT_SHA}."
echo "Digests (esto es lo que se anota en el informe como evidencia de versionado):"
for componente in app caddy opa; do
    gcloud artifacts docker images describe \
        "${REGISTRY}/${componente}:${VERSION}" \
        --format="value(image_summary.digest)" 2>/dev/null \
        | sed "s|^|  ${componente}  |"
done

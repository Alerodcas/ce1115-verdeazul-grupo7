# =============================================================================
#  Imagen del motor de decisión — OPA (PDP), Zona 2
#  CE-1115 Proyecto Parte 2 · Grupo 7
#
#  Corre como contenedor sidecar junto a la aplicación. Escucha SOLO en
#  127.0.0.1:8181, así que no es alcanzable desde fuera de la instancia
#  (Parte 1, frontera F3).
#
#  Las políticas se hornean en la imagen a propósito: así la versión de la
#  imagen identifica también la versión de las reglas, que es lo que el
#  enunciado pide poder rastrear (§3.2).
# =============================================================================

FROM openpolicyagent/opa:1.22.2-static

ARG APP_VERSION=dev
ARG GIT_SHA=unknown

LABEL org.opencontainers.image.title="verdeazul-opa" \
      org.opencontainers.image.description="Motor de decision (PDP) con las reglas RBAC2 + ABAC de la matriz" \
      org.opencontainers.image.vendor="Grupo 7 Byte Busters — CE-1115 ITCR" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}"

COPY policies /policies

# La imagen `-static` se basa en distroless: 65532 es su usuario sin privilegios.
USER 65532:65532

EXPOSE 8181

# --addr 127.0.0.1:8181  → no escucha en la interfaz externa de la instancia.
# --log-level error      → las decisiones se registran en la bitácora de la
#                          aplicación, no aquí; así no se duplica información
#                          del negocio en los logs de la plataforma.
ENTRYPOINT ["/opa"]
CMD ["run", "--server", \
     "--addr", "127.0.0.1:8181", \
     "--log-level", "error", \
     "--set", "decision_logs.console=false", \
     "/policies"]

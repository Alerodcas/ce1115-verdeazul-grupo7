# =============================================================================
#  Imagen del proxy inverso — Caddy (Zona 1: perímetro)
#  CE-1115 Proyecto Parte 2 · Grupo 7
#
#  Se construye Caddy con xcaddy porque la imagen oficial no trae el módulo de
#  límite de tasa, y ese límite es parte de la frontera F1 del diseño.
#
#  SI LA CONSTRUCCIÓN FALLA (el módulo no compila, no hay red hacia el proxy de
#  Go, etc.), hay un plan B inmediato: comentar la etapa `builder`, cambiar la
#  etapa final por `FROM caddy:2.9-alpine` y quitar el bloque `rate_limit` del
#  Caddyfile. El sistema queda funcionando; se anota como desviación.
# =============================================================================

# --- Etapa 1: compilar Caddy con el módulo de límite de tasa -----------------
FROM caddy:2.9-builder-alpine AS builder

RUN xcaddy build \
    --with github.com/mholt/caddy-ratelimit


# --- Etapa 2: imagen final ---------------------------------------------------
FROM caddy:2.9-alpine AS runtime

ARG APP_VERSION=dev
ARG GIT_SHA=unknown

LABEL org.opencontainers.image.title="verdeazul-caddy" \
      org.opencontainers.image.description="Proxy inverso de ingreso: limites, cabeceras y unico punto expuesto" \
      org.opencontainers.image.vendor="Grupo 7 Byte Busters — CE-1115 ITCR" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}"

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
COPY Caddyfile /etc/caddy/Caddyfile

# --- Usuario sin privilegios -------------------------------------------------
# La imagen oficial de Caddy corre como root. Aquí no: el proceso no necesita
# puertos privilegiados (escucha en 8080) ni escribir en /etc.
RUN addgroup -g 10001 -S verdeazul \
    && adduser -u 10001 -S -G verdeazul -H -s /sbin/nologin verdeazul \
    && mkdir -p /data /config \
    && chown -R 10001:10001 /data /config \
    && caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

USER 10001:10001

ENV XDG_DATA_HOME=/data \
    XDG_CONFIG_HOME=/config \
    PORT=8080 \
    APP_PORT=8000

EXPOSE 8080

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]

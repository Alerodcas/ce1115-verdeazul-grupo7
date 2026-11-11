# Arquitectura desplegada

**Borrador de la sección 5.1.1 del Informe de Implementación · Responsable: Alejandra**

> Daniel consolida el informe final. Este archivo es el texto y el diagrama
> listos para pegar; conviene no reescribirlo en otro lado para que no se
> desincronicen.

---

## 1. Qué se construyó

El sistema corre como **un servicio de Google Cloud Run con tres contenedores**
en la misma instancia, apoyado en **Neon** (PostgreSQL gestionado) y **Secret
Manager**. Las imágenes viven en **Artifact Registry**, versionadas con etiqueta
explícita.

Los tres contenedores comparten la interfaz de red de la instancia. Eso tiene una
consecuencia que vale la pena enunciar porque es la que sostiene la separación
del diseño: **solo el puerto declarado por el contenedor de ingreso recibe
tráfico de internet.** La aplicación y el motor de decisión escuchan en puertos
que no existen fuera de la instancia.

| Componente desplegado | Imagen | Zona de la Parte 1 | Papel |
|---|---|---|---|
| `caddy` | `REGION-docker.pkg.dev/PROYECTO/verdeazul/caddy:vX.Y.Z` | Zona 1, perímetro | Único contenedor expuesto. Límite de tasa y de tamaño, métodos permitidos, cabeceras de seguridad. |
| `app` | `…/verdeazul/app:vX.Y.Z` | Zona 2, aplicación | Django + DRF. Autenticación, sesión, validación de entrada, punto de aplicación de la política (PEP). |
| `opa` | `…/verdeazul/opa:vX.Y.Z` | Zona 2, aplicación | Motor de decisión (PDP). Reglas RBAC2 + ABAC en Rego. Solo loopback. |
| Neon PostgreSQL | servicio gestionado | Zona 3, datos | Datos del negocio, sesiones, contadores del control por historial y bitácora. |
| Secret Manager | servicio gestionado | Zona 3, secretos | Los tres secretos del sistema, inyectados como variables de entorno. |

---

## 2. Cómo se comunican

| Frontera (Parte 1) | Cómo quedó implementada | Dónde verificarlo |
|---|---|---|
| **F1** Internet → perímetro | TLS 1.2+ terminado por el front end de Google con certificado gestionado. Caddy aplica límite de tasa por dirección de origen (dos ventanas: 120/min y 1200/h), tamaño máximo de 2 MB y lista de métodos permitidos. | `caddy/Caddyfile` |
| **F2** Perímetro → aplicación | Conexión por la red local de la instancia. Caddy reenvía `X-Forwarded-Proto` y la dirección real del cliente. Django revalida todo: tipos, formato, token CSRF y sesión. | `caddy/Caddyfile`, `app/config/settings.py` |
| **F3** Aplicación → motor de decisión | HTTP solo por `127.0.0.1:8181`. El contenedor `opa` no declara puerto de ingreso, así que no es alcanzable desde fuera. La entrada de la decisión se arma en el servidor con datos leídos de la base. | `app/authz/pdp.py`, `deploy/service.yaml` |
| **F4** Aplicación → base de datos | TLS obligatorio (`sslmode=require`) hacia Neon. Credencial en Secret Manager, nunca en el código. | `app/config/settings.py`, `deploy/service.yaml` |
| **F5** Aplicación → secretos | Cloud Run resuelve las referencias de Secret Manager con la identidad de la cuenta de servicio del servicio, que solo tiene permiso de lectura sobre esos tres secretos. | `deploy/setup-gcp.sh` |
| **F6** Aplicación → registro externo | **No implementada en esta entrega.** Ver `docs/DESVIACIONES.md` (D-03). | — |

### Separación de identidades

| Identidad | Puede | No puede |
|---|---|---|
| `verdeazul-run` (ejecuta el servicio) | Leer los tres secretos | Publicar imágenes, cambiar el servicio, crear secretos |
| `verdeazul-deploy` (construye y despliega) | Publicar imágenes, actualizar el servicio | **Leer ningún secreto** |

Es la regla 1 de gestión de secretos de la Parte 1: quien tiene acceso al código
no tiene acceso a producción.

---

## 3. Diagrama de componentes

### Para el informe en LaTeX

Usa los mismos paquetes de TikZ que el documento de arquitectura de la Parte 1
(`positioning`, `arrows.meta`, `fit`, `backgrounds`), así que se pega tal cual.

```latex
\begin{figure}[H]
\centering
\resizebox{\textwidth}{!}{%
\begin{tikzpicture}[
  caja/.style={draw, rounded corners=2pt, minimum width=3cm, minimum height=1cm,
               align=center, font=\footnotesize, fill=white},
  zona/.style={draw, dashed, rounded corners=4pt, inner sep=7pt, font=\scriptsize},
  flecha/.style={-{Stealth[length=2mm]}, thick},
  etq/.style={font=\scriptsize, fill=white, inner sep=1pt}
]
\node[caja] (cli) at (0,0) {Navegador\\(6 roles)};
\node[caja] (gfe) at (4.3,0) {Front end de Google\\termina TLS};
\node[caja] (cad) at (8.8,0) {Caddy\\contenedor de ingreso\\\texttt{:8080}};
\node[caja] (app) at (13.6,0) {Django + DRF (PEP)\\\texttt{127.0.0.1:8000}};
\node[caja] (opa) at (13.6,2.7) {OPA (PDP)\\\texttt{127.0.0.1:8181}};
\node[caja] (neo) at (13.6,-3.1) {Neon PostgreSQL 17\\datos y bit\'acora};
\node[caja] (sec) at (8.8,-3.1) {Secret Manager\\3 secretos};
\node[caja] (reg) at (4.3,-3.1) {Artifact Registry\\im\'agenes \texttt{vX.Y.Z}};

\begin{scope}[on background layer]
  \node[zona, fit=(cad), label={[font=\scriptsize]above:Zona 1: per\'imetro}] {};
  \node[zona, fit=(app)(opa), label={[font=\scriptsize]above:Zona 2: aplicaci\'on}] {};
  \node[zona, fit=(neo)(sec), label={[font=\scriptsize]below:Zona 3: datos y secretos}] {};
  \node[zona, fit=(cad)(app)(opa), inner sep=16pt,
        label={[font=\scriptsize]below left:Instancia de Cloud Run (red local compartida)}] {};
\end{scope}
\node[font=\scriptsize, above=0.9cm of cli] {Zona 0: no confiable};

\draw[flecha] (cli) -- node[etq, above] {HTTPS (F1)} (gfe);
\draw[flecha] (gfe) -- node[etq, above] {HTTP interno} (cad);
\draw[flecha] (cad) -- node[etq, above] {loopback (F2)} (app);
\draw[flecha] (app) -- node[etq, right] {loopback (F3)} (opa);
\draw[flecha] (app) -- node[etq, right] {TLS, \texttt{sslmode=require} (F4)} (neo);
\draw[flecha] (app) -- node[etq, above] {variables inyectadas (F5)} (sec);
\draw[flecha] (reg) -- node[etq, left] {despliegue} ++(0,1.6);
\end{tikzpicture}}
\caption{Arquitectura realmente desplegada. Las fronteras F1 a F5 corresponden a
las de la Parte 1; F6 no se implementó (ver secci\'on de desviaciones).}
\label{fig:desplegada}
\end{figure}
```

### Versión rápida, para la presentación

```
  Zona 0            Zona 1                Zona 2                 Zona 3
 ────────   ───────────────────   ─────────────────────   ──────────────────
                 ┌─────────────────────────────────────┐
 navegador       │     instancia de Cloud Run          │
     │  HTTPS    │                                     │
     ▼           │  ┌───────┐ loopback ┌────────────┐  │  TLS   ┌──────────┐
 front end ──────┼─►│ caddy │─────────►│ app  (PEP) │──┼───────►│   Neon   │
 de Google       │  │ :8080 │          │   :8000    │  │        │ Postgres │
 (TLS)           │  └───────┘          └──────┬─────┘  │        └──────────┘
                 │                     loopback│       │
                 │                     ┌───────▼────┐  │        ┌──────────┐
                 │                     │ opa  (PDP) │  │◄───────│  Secret  │
                 │                     │   :8181    │  │ inyecta│ Manager  │
                 │                     └────────────┘  │        └──────────┘
                 └─────────────────────────────────────┘
```

---

## 4. Seguridad heredada de la plataforma

> Insumo para la sección 5.1.4, que escribe **Eder**. Aquí queda solo lo que se
> observa desde la infraestructura; el análisis del modelo de responsabilidad
> compartida es suyo.

### Cloud Run

| Lo pone Google | Queda del lado del equipo |
|---|---|
| Certificado TLS gestionado para `*.run.app` y su renovación | Que la aplicación no acepte HTTP ni confíe en cabeceras falsificadas |
| Aislamiento de la instancia y parcheo del sistema anfitrión | El contenido de las imágenes: dependencias, usuario sin root, CVE |
| Escalado y terminación de conexiones | El límite de instancias (`maxScale`) y el consumo |
| IAM del servicio y de las cuentas | Que los permisos sean los mínimos y estén separados |

### Neon

Lo que ofrece el plan gratuito, comprobado en la documentación del proveedor:

- Cifrado en reposo con AES-256.
- Cifrado en tránsito obligatorio (TLS; admite `verify-full`).
- Exigencia de contraseñas con al menos 60 bits de entropía para los roles de
  PostgreSQL.
- Un proxy de conexión que corta intentos de inicio de sesión no autorizados.

Lo que **no** está disponible en el plan gratuito y por tanto es un riesgo
declarado, no mitigado:

- **IP Allow** (restringir las direcciones de origen que pueden conectarse) está
  en el plan Scale. Cualquiera con la cadena de conexión puede conectarse desde
  cualquier lugar. Es la razón de fondo por la que esa cadena vive en Secret
  Manager y por la que `gitleaks` tiene una regla propia para detectarla.
- **Ramas protegidas** están en los planes de pago, así que no se puede impedir
  por configuración que alguien reinicie la rama con los datos.

Límites del plan gratuito que conviene tener presentes porque suspenden el
*compute* hasta el mes siguiente: 100 horas de cómputo, 0,5 GB de
almacenamiento y 5 GB de salida al mes. **No hacer pruebas de carga contra Neon
antes de la presentación.**

### Lo que ningún proveedor cubre

Ni Google ni Neon protegen contra una consulta mal construida, un permiso
excesivo en la matriz o una credencial filtrada. Esos tres riesgos siguen siendo
del equipo, y son exactamente los que atacan el motor de autorización (Kevin),
la gestión de secretos (Eder) y la bitácora (Daniel).

---

## 5. Evidencias a recolectar

| Evidencia | Dónde se obtiene | Para qué criterio |
|---|---|---|
| Navegador con candado y URL `*.run.app` | Abrir el sistema desde una red ajena | Despliegue funcional (16 pts) |
| Consola de Cloud Run mostrando los 3 contenedores de la revisión | Cloud Run → servicio → Revisiones → Contenedores | Arquitectura implementada (parte de los 25 pts) |
| Artifact Registry con las etiquetas `vX.Y.Z` y `sha-…` | Artifact Registry → repositorio `verdeazul` | Contenedores y versionado (10 pts) |
| Salida de `gcloud run services describe` con las referencias a secretos | Terminal | Gestión de secretos (12 pts) |
| `curl -sI http://…` redirigiendo a HTTPS | Terminal | TLS en todo el tráfico |

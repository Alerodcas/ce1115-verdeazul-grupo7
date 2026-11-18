# Evidencias del despliegue

Capturas e salidas de terminal que respaldan el Informe de Implementación.
Van en el repositorio a propósito: así quedan versionadas junto al despliegue
que prueban, y Daniel las tiene con un `git pull` para consolidar el informe.

**Regla:** ninguna captura muestra el valor de un secreto. Nombres, versiones y
fechas sí; valores nunca. Antes de guardar una, revisar que no haya quedado una
cadena de conexión ni una clave en pantalla.

## Índice

| Archivo | Qué prueba | Criterio del enunciado |
|---|---|---|
| `E01-url-publica-candado.png` | El sistema abre desde internet por HTTPS, con el candado y la URL `*.run.app` visibles | Despliegue funcional (16 pts) |
| `E02-cloudrun-tres-contenedores.png` | La revisión activa corre **los tres contenedores** del diseño: `caddy`, `app`, `opa` | Arquitectura implementada (parte de 25 pts) |
| `E03-artifact-registry-etiquetas.png` | Las tres imágenes publicadas con etiqueta de versión explícita y `sha-<commit>`, sin `latest` | Contenedores y registro (10 pts) |
| `E04-verificacion-terminal.png` | `/ready` responde `ok`, las cabeceras de seguridad de Caddy están presentes, y HTTP redirige a HTTPS | Despliegue + controles |
| `E05-secret-manager.png` | Los tres secretos existen en Secret Manager, con sus versiones | Gestión de secretos (12 pts) |
| `E06-permisos-separados.png` | `verdeazul-run` puede leer los secretos y `verdeazul-deploy` **no**: quien despliega no accede a producción | Gestión de secretos (12 pts) |
| `E07-ci-verde.png` | El CI pasa gitleaks, bandit, pip-audit, `check --deploy`, pruebas, `opa test`, Trivy y la comprobación de que ninguna imagen corre como root | Contenedores + informe |
| `E08-dependabot.png` | Dependabot activo y con alertas atendidas — **responsable: Eder** | Dependabot (parte de 10 pts) |

## Cómo se obtuvieron las de terminal

Los comandos exactos están en `docs/evidencias/comandos-verificacion.md`.
Cualquiera del equipo puede volver a correrlos y obtener lo mismo.

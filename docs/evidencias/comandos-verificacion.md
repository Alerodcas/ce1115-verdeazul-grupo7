# Comandos de verificación

Reproducibles por cualquier integrante. Las salidas de estos comandos son las
capturas `E04` y `E06`.

## Desde una máquina cualquiera, fuera de Google (PowerShell)

El enunciado pide comprobarlo desde una red distinta a la del despliegue.
En PowerShell hay que escribir `curl.exe`, porque `curl` es un alias de
`Invoke-WebRequest` y no entiende las banderas de Unix.

```powershell
$URL = "https://verdeazul-2wkb3ke6wq-uc.a.run.app"

curl.exe -s -w "`n" "$URL/ready"
curl.exe -sI "$URL/" | Select-String -Pattern 'HTTP/|strict-transport|content-security|x-content-type|x-frame|referrer-policy'
curl.exe -sI "http://verdeazul-2wkb3ke6wq-uc.a.run.app/" | Select-Object -First 3
```

Nota: las rutas públicas son `/health` y `/ready`, **sin la «z» final**.
Cloud Run reserva algunas rutas terminadas en `z` (`/healthz`, `/readyz`) y su
front end las responde con un 404 propio antes de que la petición llegue al
contenedor.

## Desde Cloud Shell

```bash
gcloud secrets list --format="table(name,createTime)"

gcloud run services describe verdeazul --region=us-central1 \
  --format="value(spec.template.spec.containers[].name)"

gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/$(gcloud config get-value project)/verdeazul \
  --include-tags --format="table(package,tags)"

gcloud secrets get-iam-policy verdeazul-database-url \
  --format="table(bindings.role,bindings.members)"
```

El último es el importante para el criterio de secretos: muestra que solo
`verdeazul-run` tiene `roles/secretmanager.secretAccessor`, y que
`verdeazul-deploy` —la cuenta que construye y despliega— no aparece.

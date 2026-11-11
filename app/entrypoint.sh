#!/bin/sh
# Punto de entrada de la imagen de la aplicación.
#
# Por omisión NO corre migraciones. En Cloud Run pueden levantarse varias
# instancias a la vez y dos migraciones simultáneas sobre Neon se estorban.
# Las migraciones se corren una sola vez, desde deploy/migrate.sh.
set -eu

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "entrypoint: aplicando migraciones"
    python manage.py migrate --noinput
fi

# Comprobación de configuración de despliegue de Django. Si algo quedó
# inseguro (DEBUG encendido, cookies sin Secure, SECRET_KEY débil), avisa.
python manage.py check --deploy || echo "entrypoint: 'check --deploy' reportó avisos"

exec "$@"

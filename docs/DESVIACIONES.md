# Desviaciones respecto al diseño de la Parte 1

**Insumo para la sección 5.1.5 del informe. Dueño de esa sección: Luis.**
Las que están aquí son las de **infraestructura y red** (Alejandra). Cada quien
agrega las suyas a esta misma lista para que el informe salga de un solo lugar.

> El enunciado (§4.1) dice que una desviación bien argumentada **suma**: lo que
> resta es que el sistema no se parezca al diseño y nadie lo explique. El formato
> de cada entrada es el que pide: qué cambió, por qué, y qué implicación de
> seguridad tuvo.

---

## D-01 · La terminación de TLS pasó de Caddy al front end de Google

**Diseño original.** Caddy es el único punto expuesto a internet, termina TLS y
renueva los certificados con ACME.

**Qué se hizo.** El certificado de `*.run.app` lo emite y renueva Google, y el
tráfico llega a Caddy ya descifrado por la red interna de la instancia. Caddy
corre con `auto_https off` y conserva el resto de sus funciones: límite de tasa,
límite de tamaño, métodos permitidos y cabeceras de seguridad de la respuesta.

**Por qué.** El enunciado fija Cloud Run como plataforma de ejecución, y Cloud
Run no entrega conexiones TLS crudas al contenedor: termina TLS en su propio
balanceador. Mantener ACME dentro de Caddy habría exigido un dominio propio y
un balanceador externo, fuera del alcance y de la capa gratuita.

**Implicación de seguridad.** Mixta, y conviene decirlo completo:

- *A favor:* la renovación del certificado deja de ser responsabilidad del
  equipo, que es donde más fallan los despliegues pequeños. El front end de
  Google además absorbe los ataques de volumen antes de que lleguen al
  contenedor.
- *En contra:* aparece un tramo de red —del balanceador de Google al
  contenedor— donde el tráfico viaja sin cifrar. Ese tramo está dentro de la
  infraestructura de Google y no es observable por terceros, pero deja de ser
  cifrado de extremo a extremo, que es lo que el diseño prometía.
- *Consecuencia práctica:* la aplicación ya no puede deducir el esquema de la
  conexión por sí misma y depende de la cabecera `X-Forwarded-Proto`. Confiar en
  una cabecera que puede falsificarse sería un error grave; aquí se puede confiar
  porque **el único camino hacia el contenedor pasa por el balanceador de Cloud
  Run, que reescribe esa cabecera**. Si en el futuro el servicio se expusiera por
  otra vía, esta suposición deja de valer.

---

## D-02 · Podman rootless con Quadlet → imágenes OCI en Cloud Run

**Diseño original.** Podman 5 sin privilegios de root, con Quadlet y systemd,
porque el demonio de Docker corre como root.

**Qué se hizo.** Las imágenes se construyen con Cloud Build y se ejecutan en
Cloud Run.

**Por qué.** Lo fija el enunciado (§3.1). No había elección.

**Implicación de seguridad.** El motivo por el que se eligió Podman —no tener un
demonio con privilegios en la máquina que ejecuta— se cumple igual o mejor: en
Cloud Run no hay demonio de contenedores accesible para el equipo, y el
aislamiento de la instancia lo administra Google. Lo que **sí** se perdió es el
control sobre SELinux y sobre las capacidades del contenedor, que con Quadlet se
podían afinar. Se compensa con lo que sigue bajo control del equipo y se
verifica en integración continua: imágenes mínimas, construcción en dos etapas y
**ningún contenedor corriendo como root** (hay una comprobación que hace fallar
el pipeline si alguna imagen queda con `USER` vacío o `0`).

---

## D-03 · La copia de la bitácora fuera del host no se implementó

**Diseño original.** Capas 3 y 4 de la protección de la bitácora: anclaje horario
firmado en un almacén con *Object Lock*, y copia casi en tiempo real por syslog
sobre TLS hacia un servidor de registros con credenciales distintas (frontera
F6).

**Qué se hizo.** En esta entrega la bitácora vive solo en Neon, con las capas que
sí se pueden sostener ahí: solo inserción, cadena de hashes y verificación.

**Por qué.** Un almacén con *Object Lock* y un servidor de registros aparte son
dos servicios adicionales fuera de la capa gratuita, y el enunciado acota el
despliegue a Cloud Run, Neon y Secret Manager.

**Implicación de seguridad.** Es la desviación más seria de las tres y no
conviene maquillarla. La amenaza A5 del Informe de políticas —que la bitácora la
altere alguien con permiso legítimo de escritura— queda **cubierta solo
parcialmente**: la cadena de hashes detecta una alteración aislada, pero quien
controle la base de datos completa podría recalcularla, y eso era justamente lo
que las capas 3 y 4 impedían. El riesgo queda declarado, no mitigado.

**Qué haría falta para cerrarla** (para la sección de trabajo futuro): publicar
el hash de la última entrada cada hora, firmado, en un bucket con *Object Lock* o
en cualquier almacén de escritura única fuera del proyecto. Es media jornada de
trabajo y un servicio más.

> Responsable del detalle de esta desviación: **Daniel** (bitácora). Aquí queda
> enunciada desde la infraestructura porque es ella la que no se desplegó.

---

## D-04 · OpenBao → Secret Manager de Google

**Diseño original.** OpenBao, con secretos dinámicos de corta vida, cifrado como
servicio y desello con umbral de 3 de 5 custodios.

**Qué se hizo.** Secret Manager, con tres secretos estáticos y lectura
restringida a la cuenta de servicio del servicio.

**Por qué.** Lo fija el enunciado. Además, sostener OpenBao exige un servicio
permanente con estado, incompatible con una plataforma que escala a cero.

**Implicación de seguridad.** Se pierde lo que más aportaba OpenBao: las
**credenciales dinámicas de corta vida**. La cadena de conexión a Neon es ahora
una credencial estática y de larga vida; si se filtra, sirve hasta que alguien la
rote a mano. A cambio se gana que la custodia de la clave maestra la hace Google
y no el equipo, que era el punto único de fallo que el propio diseño declaraba
como riesgo. La rotación, que antes era automática, pasa a ser un procedimiento
manual que hay que documentar.

> Responsable del detalle: **Eder** (gestión de secretos).

---

## Plantilla para las desviaciones que falten

```markdown
## D-0X · <título en una línea>

**Diseño original.** Qué decía la Parte 1, con la sección de referencia.

**Qué se hizo.** Qué quedó realmente desplegado.

**Por qué.** La razón técnica o de alcance. «Nos faltó tiempo» también es una
razón válida si se dice con claridad; inventar una justificación técnica que no
se sostiene es peor.

**Implicación de seguridad.** Qué protección se perdió o se ganó, y qué amenaza
del modelo de la Parte 1 queda sin cubrir.
```

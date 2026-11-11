# Contrato entre las partes del sistema

**Para que los cuatro frentes avancen en paralelo sin pisarse.**
Escrito por Alejandra (infraestructura) a partir del diseño de la Parte 1.
Si algo de aquí hay que cambiarlo, se cambia **en este archivo primero** y se
avisa al grupo, porque hay código de tres personas colgando de estos nombres.

---

## 1. Quién escribe qué

| Carpeta / archivo | Dueño | Estado |
|---|---|---|
| `deploy/`, `caddy/`, los tres `Dockerfile`, `.github/`, `compose.yaml` | Alejandra | hecho |
| `app/config/settings.py` | Alejandra | hecho — los demás agregan su app a `INSTALLED_APPS`, sin tocar el bloque de seguridad |
| `opa/policies/*.rego`, `app/authz/` | Kevin | andamio puesto, reglas pendientes |
| `app/certificados/` | Luis | pendiente |
| `app/negocio/`, `app/auditoria/` | Daniel | pendiente |
| Secret Manager, Dependabot | Eder | secretos creados, falta cargarlos y activar Dependabot |

Regla práctica: **una rama por frente** (`feat/authz`, `feat/certificados`,
`feat/auditoria`) y pull request contra `main`. CI corre en cada una; nada entra
a `main` con el pipeline en rojo.

---

## 2. Entidades

Siete objetos, los de la matriz de la Parte 1. Nombres de clase en el singular
y en español sin tilde, para que coincidan con lo que ya espera la política:

| Clase | `objeto_tipo` en la política | Notas del diseño |
|---|---|---|
| `Finca` | `Finca` | Tiene propietario (regla S2) y técnicos asignados (regla S1). Se desactiva, nunca se borra. |
| `Periodo` | `Periodo` | Abierto o cerrado. Solo la Gerencia lo abre y lo cierra. |
| `Medicion` | `Medicion` | Estados: `borrador`, `enviada`, `devuelta`, `aprobada`. Guarda autor y editores previos (regla C2). |
| `Enmienda` | `Enmienda` | Solicitante, autorizante, motivo y estado. Crea versión nueva, nunca sobrescribe. |
| `Certificado` | `Certificado` | Parcela + período + estado. Restricción de exclusión contra el duplicado (regla C3). |
| `Cuenta` | `Cuenta` | Solicitud escrita, ejecutor y aprobador distintos (regla C6). |
| `Bitacora` | `Bitacora` | Solo inserción. Ningún rol tiene `Update` ni `Delete`. |

**Ningún objeto tiene `Delete`.** Es una decisión explícita de la Parte 1: el
cliente debe poder rastrear cualquier certificado durante diez años.

---

## 3. Acciones

Las de la matriz, con esta ortografía exacta:

```
Create  Read  Update  Approve  Return  Download  Open  Close  Authorize  Revoke  Deactivate
```

---

## 4. Roles

Los seis de la matriz, con esta ortografía exacta (sin tildes, porque viajan como
cadenas a la política):

```
Tecnico de campo   Verificador   Administrador
Auditor externo    Dueno de finca   Gerencia de Certificacion
```

Se materializan como **grupos de Django**. `app/authz/permissions.py` los lee de
la base en cada petición y **no** los copia a la sesión: así una baja o un cambio
de rol vale de inmediato (Parte 1, «Cambio de privilegios»).

El **rol activo** —el que la persona elige cuando tiene más de uno— sí vive en la
sesión, en `request.session["rol_activo"]`. Cambiarlo tiene que rotar el
identificador de sesión.

---

## 5. Cómo se le pregunta al motor de decisión

Toda vista pasa por el PEP. Ejemplo del patrón:

```python
from rest_framework.views import APIView
from authz.permissions import PermitePorMatriz


class MedicionAprobarView(APIView):
    permission_classes = [PermitePorMatriz]
    objeto_tipo = "Medicion"
    accion = "Approve"

    def construir_atributos(self, request, obj):
        # TODO: todo esto se LEE DE LA BASE, nunca del cuerpo de la petición.
        return {
            "estado_objeto": obj.estado,
            "es_autor": obj.creada_por_id == request.user.pk,
            "fue_editor": obj.editores.filter(pk=request.user.pk).exists(),
            "mfa_reciente": mfa_en_los_ultimos_minutos(request, 5),
        }
```

El PEP arma la entrada y se la manda al PDP. La estructura está en
`app/authz/pdp.py` (`DecisionInput`) y es la que consume `opa/policies/authz.rego`.
**Si se agrega un atributo, hay que agregarlo en los dos lados.**

Atributos previstos por las celdas condicionadas:

| Atributo | Tipo | Reglas que lo usan |
|---|---|---|
| `finca_asignada` | bool | S1, C1 |
| `es_propietario` | bool | S2 |
| `periodo_abierto` | bool | C1 |
| `estado_objeto` | str | C1, C2, C3 |
| `es_autor` | bool | C1, C2, C3 |
| `fue_editor` | bool | C2 |
| `mfa_reciente` | bool | C2, C4 |
| `existe_cert_vigente` | bool | C3 |
| `solicitante` | str | C4, C6 |
| `fincas_leidas_24h` | int | C5 |

La respuesta del PDP trae `allow`, `rule_id`, `rule_ver`, `obligations` y
`reason`. **`rule_id` y `rule_ver` tienen que llegar al evento de la bitácora**:
sin ellos no se le puede explicar al auditor por qué se concedió o se negó.

---

## 6. Qué espera la infraestructura de cada app

Para que nada rompa el despliegue:

1. **Ningún secreto en el código.** Todo por `os.environ`. Si hace falta uno
   nuevo, se crea en Secret Manager y se agrega al bloque `env` de `app` en
   `deploy/service.yaml`. Avisar a Alejandra.
2. **Nada que escriba en disco.** El contenedor es efímero: lo que se escriba
   desaparece al reciclarse la instancia. Los archivos van a la base de datos.
3. **Nada que dependa de que el proceso siga vivo entre peticiones.** Cloud Run
   escala a cero. No hay tareas en segundo plano ni temporizadores en memoria.
4. **Migraciones en archivos versionados**, no a mano contra Neon. Se aplican con
   `deploy/migrate.sh`.
5. **Las pruebas tienen que correr sin red.** CI usa SQLite. Si una prueba exige
   PostgreSQL de verdad, avisar para agregar un servicio al flujo de trabajo.
6. **Dependencia nueva → `app/requirements.txt`**, con versión fijada. `pip-audit`
   corre en cada integración.

# =============================================================================
#  Política de autorización — Verdeazul Carbono S.A.
#  CE-1115 Proyecto Parte 2 · Grupo 7
#
#  DUEÑO DE ESTE ARCHIVO: Kevin (motor de autorización RBAC2 + ABAC).
#
#  Lo que hay aquí es el ANDAMIO que deja el contenedor funcionando y fija el
#  contrato con el PEP (app/authz/pdp.py). Las celdas de la matriz están
#  declaradas pero casi todas vacías: hay que llenarlas para que el criterio de
#  25 puntos se dé por cumplido.
#
#  Regla de oro: denegar por omisión. Si ninguna regla concede, la respuesta es
#  `allow = false`. Nunca agregar un `default allow := true` "temporal".
#
#  Pruebas:  opa test opa/policies -v
# =============================================================================

package verdeazul.authz

import rego.v1

# -----------------------------------------------------------------------------
# Salida: el PEP espera exactamente esta forma (ver app/authz/pdp.py, Decision)
# -----------------------------------------------------------------------------
decision := {
	"allow": allow,
	"rule_id": rule_id,
	"rule_ver": rule_ver,
	"obligations": obligations,
	"reason": reason,
}

default allow := false
default rule_id := "DENY_DEFAULT"
default rule_ver := "0"
default reason := "Ninguna regla de la matriz concede este permiso."

obligations contains "mfa_reciente" if {
	requiere_mfa
}

default requiere_mfa := false

# -----------------------------------------------------------------------------
# Vocabulario de la matriz (Parte 1, documento "Matriz de control de acceso")
# -----------------------------------------------------------------------------
roles_validos := {
	"Tecnico de campo",
	"Verificador",
	"Administrador",
	"Auditor externo",
	"Dueno de finca",
	"Gerencia de Certificacion",
}

objetos_validos := {"Finca", "Periodo", "Medicion", "Enmienda", "Certificado", "Cuenta", "Bitacora"}

# -----------------------------------------------------------------------------
# Celdas INCONDICIONALES de la matriz: rol × objeto → acciones permitidas
# -----------------------------------------------------------------------------
# TODO(Kevin): completar con TODAS las celdas de la tabla de la Parte 1.
# Lo que falte aquí se descuenta del criterio "Permisos de la matriz sin
# implementar" (§7.1 del enunciado).
permisos_simples := {
	"Tecnico de campo": {
		"Periodo": {"Read"},
	},
	"Verificador": {
		"Finca": {"Read"},
		"Periodo": {"Read"},
		"Medicion": {"Read"},
		"Enmienda": {"Read"},
		"Certificado": {"Read", "Download"},
	},
	"Administrador": {
		"Finca": {"Create", "Read", "Update", "Deactivate"},
		"Periodo": {"Read"},
	},
	"Auditor externo": {
		"Finca": {"Read"},
		"Periodo": {"Read"},
		"Medicion": {"Read"},
		"Enmienda": {"Read"},
		"Certificado": {"Read", "Download"},
		"Bitacora": {"Read"},
	},
	"Gerencia de Certificacion": {
		"Finca": {"Read"},
		"Periodo": {"Read", "Open", "Close"},
		"Medicion": {"Read"},
		"Enmienda": {"Read"},
		"Certificado": {"Read", "Revoke"},
		"Cuenta": {"Read"},
		"Bitacora": {"Read"},
	},
}

allow if {
	rol := input.rol_activo
	rol in roles_validos
	rol in object.keys(permisos_simples)
	input.objeto_tipo in object.keys(permisos_simples[rol])
	input.accion in permisos_simples[rol][input.objeto_tipo]
}

rule_id := "MATRIZ_SIMPLE" if {
	rol := input.rol_activo
	rol in object.keys(permisos_simples)
	input.objeto_tipo in object.keys(permisos_simples[rol])
	input.accion in permisos_simples[rol][input.objeto_tipo]
}

# -----------------------------------------------------------------------------
# Celdas CONDICIONADAS — C1 a C6, S1, S2
# -----------------------------------------------------------------------------
# TODO(Kevin): implementar cada una según la sección "Celdas condicionadas" de
# la matriz. Abajo queda C1 resuelta como ejemplo del patrón que hay que seguir:
# cada regla valida TODAS sus condiciones, y cada una sale de input.atributos,
# que el PEP llenó leyendo la base de datos.

# C1. Técnico de campo × Medición (Create, Update)
allow if {
	input.rol_activo == "Tecnico de campo"
	input.objeto_tipo == "Medicion"
	input.accion in {"Create", "Update"}
	input.atributos.finca_asignada == true # S1
	input.atributos.periodo_abierto == true
	input.atributos.estado_objeto in {"borrador", "devuelta"}
	input.atributos.es_autor == true
}

rule_id := "C1" if {
	input.rol_activo == "Tecnico de campo"
	input.objeto_tipo == "Medicion"
	input.accion in {"Create", "Update"}
}

rule_ver := "1" if {
	rule_id != "DENY_DEFAULT"
}

# TODO(Kevin): C2 Verificador × Medición (Approve, Return) — exige MFA reciente
#              y que no sea autor ni editor previo.
# TODO(Kevin): C3 Verificador × Certificado (Create).
# TODO(Kevin): C4 Enmienda tras el cierre (Técnico crea, Gerencia autoriza).
# TODO(Kevin): C5 Técnico × Finca (Read) con umbrales 20 y 60 de fincas en 24 h.
# TODO(Kevin): C6 Cuenta (Create, Update, Deactivate, Approve).
# TODO(Kevin): S1 Técnico × Finca (Read) solo fincas asignadas.
# TODO(Kevin): S2 Dueño de finca × todo, solo si es el propietario.

reason := "Permitido por la matriz de control de acceso." if {
	allow
}

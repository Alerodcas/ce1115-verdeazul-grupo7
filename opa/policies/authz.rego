# =============================================================================
#  Política de autorización — Verdeazul Carbono S.A.
#  CE-1115 Proyecto Parte 2 · Grupo 7
#
#  DUEÑO DE ESTE ARCHIVO: Kevin (motor de autorización RBAC2 + ABAC).
#
#  Implementación del modelo híbrido RBAC2 + ABAC:
#    - Matriz de control de acceso (P1_Matriz_grupo7.tex)
#    - Celdas incondicionales: permisos_simples
#    - Celdas condicionadas: C1 a C6, S1, S2
#
#  Regla de oro: denegar por omisión. Si ninguna regla concede, la respuesta es
#  `allow = false`. Nunca agregar un `default allow := true`.
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

default requiere_mfa := false
default alerta_c5 := false

obligations contains "mfa_reciente" if {
	requiere_mfa
}

obligations contains "alerta_frecuencia_c5" if {
	alerta_c5
}

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

# C1. Técnico de campo × Medición (Read de mediciones propias en fincas asignadas)
allow if {
	input.rol_activo == "Tecnico de campo"
	input.objeto_tipo == "Medicion"
	input.accion == "Read"
	input.atributos.finca_asignada == true # S1
	input.atributos.es_autor == true
}

rule_id := "C1" if {
	input.rol_activo == "Tecnico de campo"
	input.objeto_tipo == "Medicion"
	input.accion in {"Create", "Read", "Update"}
}

# -----------------------------------------------------------------------------
# C2. Verificador × Medición (Approve, Return)
# Separación de responsabilidades: no puede ser autor ni editor previo,
# medición debe estar enviada y exige MFA reciente (últimos 5 minutos).
# -----------------------------------------------------------------------------
allow if {
	input.rol_activo == "Verificador"
	input.objeto_tipo == "Medicion"
	input.accion in {"Approve", "Return"}
	input.atributos.estado_objeto == "enviada"
	input.atributos.es_autor == false
	input.atributos.fue_editor == false
	input.atributos.mfa_reciente == true
}

rule_id := "C2" if {
	input.rol_activo == "Verificador"
	input.objeto_tipo == "Medicion"
	input.accion in {"Approve", "Return"}
}

requiere_mfa if {
	input.rol_activo == "Verificador"
	input.objeto_tipo == "Medicion"
	input.accion in {"Approve", "Return"}
}

# -----------------------------------------------------------------------------
# C3. Verificador × Certificado (Create)
# Medición aprobada, sin certificado previo vigente en la misma parcela/período,
# y el verificador no es el autor de la medición.
# -----------------------------------------------------------------------------
allow if {
	input.rol_activo == "Verificador"
	input.objeto_tipo == "Certificado"
	input.accion == "Create"
	input.atributos.estado_objeto == "aprobada"
	input.atributos.existe_cert_vigente == false
	input.atributos.es_autor == false
}

rule_id := "C3" if {
	input.rol_activo == "Verificador"
	input.objeto_tipo == "Certificado"
	input.accion == "Create"
}

# -----------------------------------------------------------------------------
# C4. Enmienda tras el cierre
# Técnico crea solicitud con motivo en período cerrado; Gerencia autoriza si
# período cerrado y quien autoriza es distinto del solicitante.
# Técnico además puede leer sus solicitudes de enmienda propias.
# -----------------------------------------------------------------------------
allow if {
	input.rol_activo == "Tecnico de campo"
	input.objeto_tipo == "Enmienda"
	input.accion == "Create"
	input.atributos.periodo_abierto == false
	input.atributos.tiene_motivo == true
	input.atributos.finca_asignada == true
}

allow if {
	input.rol_activo == "Tecnico de campo"
	input.objeto_tipo == "Enmienda"
	input.accion == "Read"
	input.atributos.es_autor == true
}

allow if {
	input.rol_activo == "Gerencia de Certificacion"
	input.objeto_tipo == "Enmienda"
	input.accion == "Authorize"
	input.atributos.periodo_abierto == false
	input.actor != input.atributos.solicitante
}

rule_id := "C4" if {
	input.rol_activo == "Tecnico de campo"
	input.objeto_tipo == "Enmienda"
	input.accion in {"Create", "Read"}
}

rule_id := "C4" if {
	input.rol_activo == "Gerencia de Certificacion"
	input.objeto_tipo == "Enmienda"
	input.accion == "Authorize"
}

# -----------------------------------------------------------------------------
# S1 + C5. Técnico de campo × Finca (Read)
# S1: solo fincas asignadas.
# C5: control de frecuencia en 24h:
#   n <= 20: permitido.
#   20 < n <= 60: permitido con MFA reciente y genera alerta.
#   n > 60: denegado y alerta a Gerencia.
# -----------------------------------------------------------------------------
allow if {
	input.rol_activo == "Tecnico de campo"
	input.objeto_tipo == "Finca"
	input.accion == "Read"
	input.atributos.finca_asignada == true # S1
	n := input.atributos.fincas_leidas_24h
	n <= 20
}

allow if {
	input.rol_activo == "Tecnico de campo"
	input.objeto_tipo == "Finca"
	input.accion == "Read"
	input.atributos.finca_asignada == true # S1
	n := input.atributos.fincas_leidas_24h
	n > 20
	n <= 60
	input.atributos.mfa_reciente == true
}

rule_id := "C5" if {
	input.rol_activo == "Tecnico de campo"
	input.objeto_tipo == "Finca"
	input.accion == "Read"
}

alerta_c5 if {
	input.rol_activo == "Tecnico de campo"
	input.objeto_tipo == "Finca"
	input.accion == "Read"
	n := input.atributos.fincas_leidas_24h
	n > 20
}

requiere_mfa if {
	input.rol_activo == "Tecnico de campo"
	input.objeto_tipo == "Finca"
	input.accion == "Read"
	n := input.atributos.fincas_leidas_24h
	n > 20
	n <= 60
}

# -----------------------------------------------------------------------------
# C6. Cuenta (Create, Update, Deactivate, Approve)
# Administrador ejecuta si hay solicitud escrita y no es beneficiario.
# Gerencia aprueba si hay solicitud escrita y no es el ejecutor.
# -----------------------------------------------------------------------------
allow if {
	input.rol_activo == "Administrador"
	input.objeto_tipo == "Cuenta"
	input.accion in {"Create", "Update", "Deactivate"}
	input.atributos.tiene_solicitud == true
	input.actor != input.atributos.beneficiario
}

allow if {
	input.rol_activo == "Gerencia de Certificacion"
	input.objeto_tipo == "Cuenta"
	input.accion == "Approve"
	input.atributos.tiene_solicitud == true
	input.actor != input.atributos.ejecutor
}

rule_id := "C6" if {
	input.rol_activo == "Administrador"
	input.objeto_tipo == "Cuenta"
	input.accion in {"Create", "Update", "Deactivate"}
}

rule_id := "C6" if {
	input.rol_activo == "Gerencia de Certificacion"
	input.objeto_tipo == "Cuenta"
	input.accion == "Approve"
}

# -----------------------------------------------------------------------------
# S2. Dueño de finca × Finca, Período, Medición, Enmienda, Certificado
# Solo si es el propietario de la finca asociada.
# -----------------------------------------------------------------------------
allow if {
	input.rol_activo == "Dueno de finca"
	input.objeto_tipo in {"Finca", "Periodo", "Medicion", "Enmienda"}
	input.accion == "Read"
	input.atributos.es_propietario == true
}

allow if {
	input.rol_activo == "Dueno de finca"
	input.objeto_tipo == "Certificado"
	input.accion in {"Read", "Download"}
	input.atributos.es_propietario == true
}

rule_id := "S2" if {
	input.rol_activo == "Dueno de finca"
	input.objeto_tipo in {"Finca", "Periodo", "Medicion", "Enmienda", "Certificado"}
}

# -----------------------------------------------------------------------------
# Metadatos de decisión
# -----------------------------------------------------------------------------
rule_ver := "1" if {
	rule_id != "DENY_DEFAULT"
}

reason := "Permitido por la matriz de control de acceso." if {
	allow
}

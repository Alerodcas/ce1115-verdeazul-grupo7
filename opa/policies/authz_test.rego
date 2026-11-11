# Pruebas de la política. Se ejecutan en integración continua: si una se cae,
# no se despliega.
#
# DUEÑO: Kevin. La meta es que cada celda de la matriz tenga su prueba — tanto
# el caso que concede como el que deniega. Eso es lo que llena la tabla de
# cobertura de la sección 5.1.6 del informe.

package verdeazul.authz_test

import data.verdeazul.authz
import rego.v1

# --- Denegar por omisión -----------------------------------------------------

test_sin_rol_se_deniega if {
	not authz.allow with input as {
		"rol_activo": "",
		"objeto_tipo": "Medicion",
		"accion": "Read",
		"atributos": {},
	}
}

test_rol_inventado_se_deniega if {
	not authz.allow with input as {
		"rol_activo": "Jefe supremo",
		"objeto_tipo": "Certificado",
		"accion": "Revoke",
		"atributos": {},
	}
}

# --- Celdas incondicionales --------------------------------------------------

test_auditor_lee_bitacora if {
	authz.allow with input as {
		"rol_activo": "Auditor externo",
		"objeto_tipo": "Bitacora",
		"accion": "Read",
		"atributos": {},
	}
}

test_administrador_no_lee_bitacora if {
	not authz.allow with input as {
		"rol_activo": "Administrador",
		"objeto_tipo": "Bitacora",
		"accion": "Read",
		"atributos": {},
	}
}

test_tecnico_no_emite_certificado if {
	not authz.allow with input as {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Certificado",
		"accion": "Create",
		"atributos": {},
	}
}

# --- C1: Técnico × Medición --------------------------------------------------

test_c1_tecnico_crea_medicion_en_periodo_abierto if {
	authz.allow with input as {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Medicion",
		"accion": "Create",
		"atributos": {
			"finca_asignada": true,
			"periodo_abierto": true,
			"estado_objeto": "borrador",
			"es_autor": true,
		},
	}
}

test_c1_periodo_cerrado_se_deniega if {
	not authz.allow with input as {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Medicion",
		"accion": "Update",
		"atributos": {
			"finca_asignada": true,
			"periodo_abierto": false,
			"estado_objeto": "borrador",
			"es_autor": true,
		},
	}
}

test_c1_finca_no_asignada_se_deniega if {
	not authz.allow with input as {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Medicion",
		"accion": "Update",
		"atributos": {
			"finca_asignada": false,
			"periodo_abierto": true,
			"estado_objeto": "borrador",
			"es_autor": true,
		},
	}
}

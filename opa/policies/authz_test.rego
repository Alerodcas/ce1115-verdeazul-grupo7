# =============================================================================
#  Pruebas de la política de autorización — Verdeazul Carbono S.A.
#  CE-1115 Proyecto Parte 2 · Grupo 7
#
#  DUEÑO: Kevin (motor de autorización RBAC2 + ABAC).
#  Cobertura permiso por permiso de la matriz (P1_Matriz_grupo7.tex)
#  Ejecución: opa test opa/policies -v
# =============================================================================

package verdeazul.authz_test

import data.verdeazul.authz
import rego.v1

# -----------------------------------------------------------------------------
# 1. Denegar por omisión y validación básica
# -----------------------------------------------------------------------------

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

test_objeto_inventado_se_deniega if {
	not authz.allow with input as {
		"rol_activo": "Administrador",
		"objeto_tipo": "Vehiculo",
		"accion": "Read",
		"atributos": {},
	}
}

test_accion_inventada_se_deniega if {
	not authz.allow with input as {
		"rol_activo": "Auditor externo",
		"objeto_tipo": "Bitacora",
		"accion": "Delete",
		"atributos": {},
	}
}

# -----------------------------------------------------------------------------
# 2. Celdas simples / incondicionales
# -----------------------------------------------------------------------------

test_tecnico_lee_periodo if {
	authz.allow with input as {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Periodo",
		"accion": "Read",
		"atributos": {},
	}
}

test_verificador_permisos_simples if {
	authz.allow with input as {
		"rol_activo": "Verificador",
		"objeto_tipo": "Finca",
		"accion": "Read",
		"atributos": {},
	}
	authz.allow with input as {
		"rol_activo": "Verificador",
		"objeto_tipo": "Periodo",
		"accion": "Read",
		"atributos": {},
	}
	authz.allow with input as {
		"rol_activo": "Verificador",
		"objeto_tipo": "Medicion",
		"accion": "Read",
		"atributos": {},
	}
	authz.allow with input as {
		"rol_activo": "Verificador",
		"objeto_tipo": "Enmienda",
		"accion": "Read",
		"atributos": {},
	}
	authz.allow with input as {
		"rol_activo": "Verificador",
		"objeto_tipo": "Certificado",
		"accion": "Read",
		"atributos": {},
	}
	authz.allow with input as {
		"rol_activo": "Verificador",
		"objeto_tipo": "Certificado",
		"accion": "Download",
		"atributos": {},
	}
}

test_administrador_gestiona_fincas_y_lee_periodo if {
	authz.allow with input as {
		"rol_activo": "Administrador",
		"objeto_tipo": "Finca",
		"accion": "Create",
		"atributos": {},
	}
	authz.allow with input as {
		"rol_activo": "Administrador",
		"objeto_tipo": "Finca",
		"accion": "Update",
		"atributos": {},
	}
	authz.allow with input as {
		"rol_activo": "Administrador",
		"objeto_tipo": "Finca",
		"accion": "Deactivate",
		"atributos": {},
	}
	authz.allow with input as {
		"rol_activo": "Administrador",
		"objeto_tipo": "Periodo",
		"accion": "Read",
		"atributos": {},
	}
}

test_auditor_lee_todo_y_descarga_certificado if {
	input_auditor := {
		"rol_activo": "Auditor externo",
		"objeto_tipo": "Bitacora",
		"accion": "Read",
		"atributos": {},
	}
	authz.allow with input as input_auditor
	authz.rule_id == "MATRIZ_SIMPLE" with input as input_auditor

	authz.allow with input as {
		"rol_activo": "Auditor externo",
		"objeto_tipo": "Finca",
		"accion": "Read",
		"atributos": {},
	}
	authz.allow with input as {
		"rol_activo": "Auditor externo",
		"objeto_tipo": "Certificado",
		"accion": "Download",
		"atributos": {},
	}
}

test_gerencia_permisos_simples if {
	authz.allow with input as {
		"rol_activo": "Gerencia de Certificacion",
		"objeto_tipo": "Periodo",
		"accion": "Open",
		"atributos": {},
	}
	authz.allow with input as {
		"rol_activo": "Gerencia de Certificacion",
		"objeto_tipo": "Periodo",
		"accion": "Close",
		"atributos": {},
	}
	authz.allow with input as {
		"rol_activo": "Gerencia de Certificacion",
		"objeto_tipo": "Certificado",
		"accion": "Revoke",
		"atributos": {},
	}
	authz.allow with input as {
		"rol_activo": "Gerencia de Certificacion",
		"objeto_tipo": "Cuenta",
		"accion": "Read",
		"atributos": {},
	}
	authz.allow with input as {
		"rol_activo": "Gerencia de Certificacion",
		"objeto_tipo": "Bitacora",
		"accion": "Read",
		"atributos": {},
	}
}

# Restricciones estrictas de rol: celdas DENIED de la matriz
test_administrador_no_lee_bitacora if {
	not authz.allow with input as {
		"rol_activo": "Administrador",
		"objeto_tipo": "Bitacora",
		"accion": "Read",
		"atributos": {},
	}
}

test_administrador_no_toca_mediciones if {
	not authz.allow with input as {
		"rol_activo": "Administrador",
		"objeto_tipo": "Medicion",
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

test_tecnico_no_lee_bitacora if {
	not authz.allow with input as {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Bitacora",
		"accion": "Read",
		"atributos": {},
	}
}

test_verificador_no_administra_cuentas if {
	not authz.allow with input as {
		"rol_activo": "Verificador",
		"objeto_tipo": "Cuenta",
		"accion": "Create",
		"atributos": {},
	}
}

# -----------------------------------------------------------------------------
# 3. C1: Técnico de campo × Medición
# -----------------------------------------------------------------------------

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
	authz.rule_id == "C1" with input as {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Medicion",
		"accion": "Create",
		"atributos": {},
	}
}

test_c1_tecnico_actualiza_medicion_devuelta if {
	authz.allow with input as {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Medicion",
		"accion": "Update",
		"atributos": {
			"finca_asignada": true,
			"periodo_abierto": true,
			"estado_objeto": "devuelta",
			"es_autor": true,
		},
	}
}

test_c1_tecnico_lee_medicion_propia if {
	authz.allow with input as {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Medicion",
		"accion": "Read",
		"atributos": {
			"finca_asignada": true,
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

test_c1_no_es_autor_se_deniega if {
	not authz.allow with input as {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Medicion",
		"accion": "Update",
		"atributos": {
			"finca_asignada": true,
			"periodo_abierto": true,
			"estado_objeto": "borrador",
			"es_autor": false,
		},
	}
}

test_c1_estado_enviada_no_permite_update if {
	not authz.allow with input as {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Medicion",
		"accion": "Update",
		"atributos": {
			"finca_asignada": true,
			"periodo_abierto": true,
			"estado_objeto": "enviada",
			"es_autor": true,
		},
	}
}

# -----------------------------------------------------------------------------
# 4. C2: Verificador × Medición (Approve, Return)
# -----------------------------------------------------------------------------

test_c2_verificador_aprueba_medicion_valida if {
	input_c2 := {
		"actor": "user-verificador-1",
		"rol_activo": "Verificador",
		"objeto_tipo": "Medicion",
		"accion": "Approve",
		"atributos": {
			"estado_objeto": "enviada",
			"es_autor": false,
			"fue_editor": false,
			"mfa_reciente": true,
		},
	}
	authz.allow with input as input_c2
	authz.rule_id == "C2" with input as input_c2
	authz.obligations == {"mfa_reciente"} with input as input_c2
}

test_c2_verificador_devuelve_medicion_valida if {
	authz.allow with input as {
		"actor": "user-verificador-1",
		"rol_activo": "Verificador",
		"objeto_tipo": "Medicion",
		"accion": "Return",
		"atributos": {
			"estado_objeto": "enviada",
			"es_autor": false,
			"fue_editor": false,
			"mfa_reciente": true,
		},
	}
}

test_c2_sod_verificador_es_autor_se_deniega if {
	# Separación de responsabilidades: el autor no puede aprobar
	not authz.allow with input as {
		"actor": "user-verificador-1",
		"rol_activo": "Verificador",
		"objeto_tipo": "Medicion",
		"accion": "Approve",
		"atributos": {
			"estado_objeto": "enviada",
			"es_autor": true,
			"fue_editor": false,
			"mfa_reciente": true,
		},
	}
}

test_c2_sod_verificador_fue_editor_se_deniega if {
	# Separación de responsabilidades: quien editó no puede aprobar
	not authz.allow with input as {
		"actor": "user-verificador-1",
		"rol_activo": "Verificador",
		"objeto_tipo": "Medicion",
		"accion": "Approve",
		"atributos": {
			"estado_objeto": "enviada",
			"es_autor": false,
			"fue_editor": true,
			"mfa_reciente": true,
		},
	}
}

test_c2_sin_mfa_reciente_se_deniega if {
	not authz.allow with input as {
		"actor": "user-verificador-1",
		"rol_activo": "Verificador",
		"objeto_tipo": "Medicion",
		"accion": "Approve",
		"atributos": {
			"estado_objeto": "enviada",
			"es_autor": false,
			"fue_editor": false,
			"mfa_reciente": false,
		},
	}
}

test_c2_estado_borrador_no_se_puede_aprobar if {
	not authz.allow with input as {
		"actor": "user-verificador-1",
		"rol_activo": "Verificador",
		"objeto_tipo": "Medicion",
		"accion": "Approve",
		"atributos": {
			"estado_objeto": "borrador",
			"es_autor": false,
			"fue_editor": false,
			"mfa_reciente": true,
		},
	}
}

test_c2_tecnico_no_puede_aprobar_medicion if {
	not authz.allow with input as {
		"actor": "user-tecnico-1",
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Medicion",
		"accion": "Approve",
		"atributos": {
			"estado_objeto": "enviada",
			"es_autor": false,
			"fue_editor": false,
			"mfa_reciente": true,
		},
	}
}

# -----------------------------------------------------------------------------
# 5. C3: Verificador × Certificado (Create)
# -----------------------------------------------------------------------------

test_c3_verificador_crea_certificado_valido if {
	input_c3 := {
		"actor": "user-verificador-1",
		"rol_activo": "Verificador",
		"objeto_tipo": "Certificado",
		"accion": "Create",
		"atributos": {
			"estado_objeto": "aprobada",
			"existe_cert_vigente": false,
			"es_autor": false,
		},
	}
	authz.allow with input as input_c3
	authz.rule_id == "C3" with input as input_c3
}

test_c3_medicion_no_aprobada_se_deniega if {
	not authz.allow with input as {
		"actor": "user-verificador-1",
		"rol_activo": "Verificador",
		"objeto_tipo": "Certificado",
		"accion": "Create",
		"atributos": {
			"estado_objeto": "enviada",
			"existe_cert_vigente": false,
			"es_autor": false,
		},
	}
}

test_c3_existe_certificado_vigente_se_deniega if {
	# Evita la doble emisión sobre la misma parcela/período
	not authz.allow with input as {
		"actor": "user-verificador-1",
		"rol_activo": "Verificador",
		"objeto_tipo": "Certificado",
		"accion": "Create",
		"atributos": {
			"estado_objeto": "aprobada",
			"existe_cert_vigente": true,
			"es_autor": false,
		},
	}
}

test_c3_sod_verificador_autor_de_medicion_se_deniega if {
	not authz.allow with input as {
		"actor": "user-verificador-1",
		"rol_activo": "Verificador",
		"objeto_tipo": "Certificado",
		"accion": "Create",
		"atributos": {
			"estado_objeto": "aprobada",
			"existe_cert_vigente": false,
			"es_autor": true,
		},
	}
}

# -----------------------------------------------------------------------------
# 6. C4: Enmienda tras el cierre
# -----------------------------------------------------------------------------

test_c4_tecnico_crea_enmienda_valida if {
	input_c4 := {
		"actor": "user-tecnico-1",
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Enmienda",
		"accion": "Create",
		"atributos": {
			"periodo_abierto": false,
			"tiene_motivo": true,
			"finca_asignada": true,
		},
	}
	authz.allow with input as input_c4
	authz.rule_id == "C4" with input as input_c4
}

test_c4_tecnico_lee_enmienda_propia if {
	authz.allow with input as {
		"actor": "user-tecnico-1",
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Enmienda",
		"accion": "Read",
		"atributos": {
			"es_autor": true,
		},
	}
}

test_c4_tecnico_crea_enmienda_periodo_abierto_se_deniega if {
	# Si el período está abierto, se corrige en medición (C1), no con enmienda
	not authz.allow with input as {
		"actor": "user-tecnico-1",
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Enmienda",
		"accion": "Create",
		"atributos": {
			"periodo_abierto": true,
			"tiene_motivo": true,
			"finca_asignada": true,
		},
	}
}

test_c4_tecnico_crea_enmienda_sin_motivo_se_deniega if {
	not authz.allow with input as {
		"actor": "user-tecnico-1",
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Enmienda",
		"accion": "Create",
		"atributos": {
			"periodo_abierto": false,
			"tiene_motivo": false,
			"finca_asignada": true,
		},
	}
}

test_c4_gerencia_autoriza_enmienda_valida if {
	input_c4_gerencia := {
		"actor": "user-gerente-1",
		"rol_activo": "Gerencia de Certificacion",
		"objeto_tipo": "Enmienda",
		"accion": "Authorize",
		"atributos": {
			"periodo_abierto": false,
			"solicitante": "user-tecnico-1",
		},
	}
	authz.allow with input as input_c4_gerencia
	authz.rule_id == "C4" with input as input_c4_gerencia
}

test_c4_sod_gerencia_autoriza_su_propia_solicitud_se_deniega if {
	# Doble control: quien autoriza no puede ser quien solicitó
	not authz.allow with input as {
		"actor": "user-gerente-1",
		"rol_activo": "Gerencia de Certificacion",
		"objeto_tipo": "Enmienda",
		"accion": "Authorize",
		"atributos": {
			"periodo_abierto": false,
			"solicitante": "user-gerente-1",
		},
	}
}

# -----------------------------------------------------------------------------
# 7. S1 y C5: Técnico de campo × Finca (Read) y Control de Frecuencia
# -----------------------------------------------------------------------------

test_s1_c5_tecnico_frecuencia_normal if {
	input_c5_bajo := {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Finca",
		"accion": "Read",
		"atributos": {
			"finca_asignada": true,
			"fincas_leidas_24h": 15,
		},
	}
	authz.allow with input as input_c5_bajo
	authz.rule_id == "C5" with input as input_c5_bajo
	obs := authz.obligations with input as input_c5_bajo
	not ("alerta_frecuencia_c5" in obs)
}

test_s1_finca_no_asignada_se_deniega if {
	not authz.allow with input as {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Finca",
		"accion": "Read",
		"atributos": {
			"finca_asignada": false,
			"fincas_leidas_24h": 5,
		},
	}
}

test_c5_frecuencia_media_con_mfa_permite_y_alerta if {
	input_c5_medio := {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Finca",
		"accion": "Read",
		"atributos": {
			"finca_asignada": true,
			"fincas_leidas_24h": 35,
			"mfa_reciente": true,
		},
	}
	authz.allow with input as input_c5_medio
	obs := authz.obligations with input as input_c5_medio
	"mfa_reciente" in obs
	"alerta_frecuencia_c5" in obs
}

test_c5_frecuencia_media_sin_mfa_se_deniega if {
	not authz.allow with input as {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Finca",
		"accion": "Read",
		"atributos": {
			"finca_asignada": true,
			"fincas_leidas_24h": 35,
			"mfa_reciente": false,
		},
	}
}

test_c5_frecuencia_alta_excede_umbral_se_deniega if {
	input_c5_alto := {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Finca",
		"accion": "Read",
		"atributos": {
			"finca_asignada": true,
			"fincas_leidas_24h": 61,
			"mfa_reciente": true,
		},
	}
	not authz.allow with input as input_c5_alto
	obs := authz.obligations with input as input_c5_alto
	"alerta_frecuencia_c5" in obs
}

# -----------------------------------------------------------------------------
# 8. C6: Cuenta (Create, Update, Deactivate, Approve)
# -----------------------------------------------------------------------------

test_c6_administrador_crea_cuenta_valida if {
	input_c6 := {
		"actor": "user-admin-1",
		"rol_activo": "Administrador",
		"objeto_tipo": "Cuenta",
		"accion": "Create",
		"atributos": {
			"tiene_solicitud": true,
			"beneficiario": "user-nuevo-2",
		},
	}
	authz.allow with input as input_c6
	authz.rule_id == "C6" with input as input_c6
}

test_c6_administrador_actualiza_y_desactiva_cuenta if {
	authz.allow with input as {
		"actor": "user-admin-1",
		"rol_activo": "Administrador",
		"objeto_tipo": "Cuenta",
		"accion": "Update",
		"atributos": {
			"tiene_solicitud": true,
			"beneficiario": "user-empleado-2",
		},
	}
	authz.allow with input as {
		"actor": "user-admin-1",
		"rol_activo": "Administrador",
		"objeto_tipo": "Cuenta",
		"accion": "Deactivate",
		"atributos": {
			"tiene_solicitud": true,
			"beneficiario": "user-empleado-2",
		},
	}
}

test_c6_sod_administrador_ejecuta_para_si_mismo_se_deniega if {
	# El ejecutor no puede ser el beneficiario de la cuenta
	not authz.allow with input as {
		"actor": "user-admin-1",
		"rol_activo": "Administrador",
		"objeto_tipo": "Cuenta",
		"accion": "Create",
		"atributos": {
			"tiene_solicitud": true,
			"beneficiario": "user-admin-1",
		},
	}
}

test_c6_administrador_sin_solicitud_se_deniega if {
	not authz.allow with input as {
		"actor": "user-admin-1",
		"rol_activo": "Administrador",
		"objeto_tipo": "Cuenta",
		"accion": "Create",
		"atributos": {
			"tiene_solicitud": false,
			"beneficiario": "user-nuevo-2",
		},
	}
}

test_c6_gerencia_aprueba_cuenta_valida if {
	input_c6_apr := {
		"actor": "user-gerente-1",
		"rol_activo": "Gerencia de Certificacion",
		"objeto_tipo": "Cuenta",
		"accion": "Approve",
		"atributos": {
			"tiene_solicitud": true,
			"ejecutor": "user-admin-1",
		},
	}
	authz.allow with input as input_c6_apr
	authz.rule_id == "C6" with input as input_c6_apr
}

test_c6_sod_gerencia_aprueba_su_propia_ejecucion_se_deniega if {
	# Quien aprueba no puede ser quien ejecutó
	not authz.allow with input as {
		"actor": "user-gerente-1",
		"rol_activo": "Gerencia de Certificacion",
		"objeto_tipo": "Cuenta",
		"accion": "Approve",
		"atributos": {
			"tiene_solicitud": true,
			"ejecutor": "user-gerente-1",
		},
	}
}

# -----------------------------------------------------------------------------
# 9. S2: Dueño de finca × Todo
# -----------------------------------------------------------------------------

test_s2_dueno_lee_recursos_de_su_finca if {
	input_s2_finca := {
		"rol_activo": "Dueno de finca",
		"objeto_tipo": "Finca",
		"accion": "Read",
		"atributos": {"es_propietario": true},
	}
	authz.allow with input as input_s2_finca
	authz.rule_id == "S2" with input as input_s2_finca

	authz.allow with input as {
		"rol_activo": "Dueno de finca",
		"objeto_tipo": "Periodo",
		"accion": "Read",
		"atributos": {"es_propietario": true},
	}
	authz.allow with input as {
		"rol_activo": "Dueno de finca",
		"objeto_tipo": "Medicion",
		"accion": "Read",
		"atributos": {"es_propietario": true},
	}
	authz.allow with input as {
		"rol_activo": "Dueno de finca",
		"objeto_tipo": "Enmienda",
		"accion": "Read",
		"atributos": {"es_propietario": true},
	}
	authz.allow with input as {
		"rol_activo": "Dueno de finca",
		"objeto_tipo": "Certificado",
		"accion": "Read",
		"atributos": {"es_propietario": true},
	}
	authz.allow with input as {
		"rol_activo": "Dueno de finca",
		"objeto_tipo": "Certificado",
		"accion": "Download",
		"atributos": {"es_propietario": true},
	}
}

test_s2_dueno_no_propietario_se_deniega if {
	# Restricción estricta de propiedad entre fincas competidoras
	not authz.allow with input as {
		"rol_activo": "Dueno de finca",
		"objeto_tipo": "Finca",
		"accion": "Read",
		"atributos": {"es_propietario": false},
	}
	not authz.allow with input as {
		"rol_activo": "Dueno de finca",
		"objeto_tipo": "Certificado",
		"accion": "Download",
		"atributos": {"es_propietario": false},
	}
}

test_s2_dueno_no_puede_crear_ni_editar if {
	not authz.allow with input as {
		"rol_activo": "Dueno de finca",
		"objeto_tipo": "Medicion",
		"accion": "Create",
		"atributos": {"es_propietario": true},
	}
	not authz.allow with input as {
		"rol_activo": "Dueno de finca",
		"objeto_tipo": "Finca",
		"accion": "Update",
		"atributos": {"es_propietario": true},
	}
}

test_s2_dueno_no_lee_bitacora_ni_cuentas if {
	not authz.allow with input as {
		"rol_activo": "Dueno de finca",
		"objeto_tipo": "Bitacora",
		"accion": "Read",
		"atributos": {"es_propietario": true},
	}
	not authz.allow with input as {
		"rol_activo": "Dueno de finca",
		"objeto_tipo": "Cuenta",
		"accion": "Read",
		"atributos": {"es_propietario": true},
	}
}

# -----------------------------------------------------------------------------
# 10. Estructura completa de decision
# -----------------------------------------------------------------------------

test_objeto_decision_completo if {
	dec := authz.decision with input as {
		"actor": "user-verificador-1",
		"rol_activo": "Verificador",
		"objeto_tipo": "Medicion",
		"accion": "Approve",
		"atributos": {
			"estado_objeto": "enviada",
			"es_autor": false,
			"fue_editor": false,
			"mfa_reciente": true,
		},
	}
	dec.allow == true
	dec.rule_id == "C2"
	dec.rule_ver == "1"
	dec.reason == "Permitido por la matriz de control de acceso."
	"mfa_reciente" in dec.obligations
}

test_objeto_decision_denegado_por_defecto if {
	dec := authz.decision with input as {
		"rol_activo": "Tecnico de campo",
		"objeto_tipo": "Bitacora",
		"accion": "Read",
		"atributos": {},
	}
	dec.allow == false
	dec.rule_id == "DENY_DEFAULT"
	dec.rule_ver == "0"
	dec.reason == "Ninguna regla de la matriz concede este permiso."
}

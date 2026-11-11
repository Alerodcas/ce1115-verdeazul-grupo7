"""Cliente del punto de decisión (PDP).

Parte 1, frontera F3: la aplicación (PEP) consulta al motor OPA **solo por
loopback**. OPA corre como contenedor sidecar en la misma instancia de
Cloud Run, así que comparte la interfaz de red local y no se expone a internet.

Dos reglas que no se negocian:

1. La entrada de la decisión se arma **en el servidor**, con datos leídos de la
   base de datos. Nunca con la finca, el rol o el estado que declare el cliente.
2. Si el motor no responde, o responde algo que no se entiende, se **deniega**
   (falla cerrada). Un PDP caído no abre el sistema.

Dueño del archivo: Kevin (motor de autorización).
Lo que está aquí es el andamio de infraestructura: el transporte y el contrato.
Las reglas en Rego van en opa/policies/.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Decision:
    """Lo que devuelve el PDP."""

    allow: bool
    rule_id: str = "UNKNOWN"
    rule_ver: str = "0"
    obligations: list[str] = field(default_factory=list)  # p. ej. ["mfa_reciente"]
    reason: str = ""


DENY_ENGINE_DOWN = Decision(
    allow=False,
    rule_id="FAIL_CLOSED",
    rule_ver="0",
    reason="El motor de decisión no respondió; se deniega por omisión.",
)


@dataclass
class DecisionInput:
    """Contrato de entrada del PDP. No agregar campos que vengan del cliente.

    Los nombres de los campos son los que consume la política en Rego; si se
    cambian aquí, hay que cambiarlos en opa/policies/authz.rego y en las
    pruebas generadas desde la matriz.
    """

    actor: str  # identificador del usuario (UUID), no su nombre
    roles: list[str]  # roles asignados y vigentes, leídos de la base
    rol_activo: str  # el rol que la persona eligió en esta sesión
    accion: str  # Create, Read, Update, Approve, Return, Download, ...
    objeto_tipo: str  # Finca, Periodo, Medicion, Enmienda, Certificado, Cuenta, Bitacora
    objeto_id: str | None = None
    atributos: dict[str, Any] = field(default_factory=dict)
    # atributos esperados según la matriz (Parte 1, "Celdas condicionadas"):
    #   finca_asignada: bool        S1
    #   es_propietario: bool        S2
    #   periodo_abierto: bool       C1
    #   estado_objeto: str          C1, C2, C3
    #   es_autor: bool              C1, C2, C3
    #   fue_editor: bool            C2
    #   mfa_reciente: bool          C2, C4
    #   existe_cert_vigente: bool   C3
    #   solicitante: str            C4, C6
    #   fincas_leidas_24h: int      C5

    def as_payload(self) -> dict[str, Any]:
        return {"input": asdict(self)}


def decidir(entrada: DecisionInput) -> Decision:
    """Pregunta al PDP. Nunca lanza excepción hacia arriba: deniega."""
    url = f"{settings.OPA_URL}/v1/data/{settings.OPA_DECISION_PATH}"
    try:
        respuesta = requests.post(
            url,
            json=entrada.as_payload(),
            timeout=settings.OPA_TIMEOUT_SECONDS,
        )
        respuesta.raise_for_status()
        resultado = respuesta.json().get("result")
    except Exception:
        # No se registra el contenido de la petición: puede traer datos del negocio.
        logger.exception("Fallo al consultar el PDP en %s", url)
        return DENY_ENGINE_DOWN

    if not isinstance(resultado, dict) or "allow" not in resultado:
        logger.error("El PDP devolvió una respuesta que no se entiende: %r", resultado)
        return DENY_ENGINE_DOWN

    return Decision(
        allow=bool(resultado.get("allow")),
        rule_id=str(resultado.get("rule_id", "UNKNOWN")),
        rule_ver=str(resultado.get("rule_ver", "0")),
        obligations=list(resultado.get("obligations", [])),
        reason=str(resultado.get("reason", "")),
    )

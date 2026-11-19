"""Hace visible la decisión del PEP en la respuesta de la API.

El PEP (`authz.permissions.PermitePorMatriz`) ya guarda la decisión del PDP en
`request.decision_authz`, y la bitácora la registra, pero la respuesta al cliente
solo decía «No autorizado.». Este middleware copia esa misma decisión a cabeceras
para que la interfaz pueda mostrar qué regla concedió o negó cada acción.

No decide nada ni cambia el cuerpo de ninguna respuesta: solo informa lo que el
PEP ya resolvió. Si una vista no consultó al PDP, no agrega nada.
"""

from __future__ import annotations

import re

_NO_SEGURO = re.compile(r"[^A-Za-z0-9_.\-]")


def _limpio(valor) -> str:
    """Solo caracteres seguros en una cabecera; el resto se descarta."""
    return _NO_SEGURO.sub("", str(valor))[:60]


class DecisionEnCabeceras:
    CABECERAS = ("X-Authz-Permitido", "X-Authz-Regla", "X-Authz-Version", "X-Authz-Obligaciones")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        contexto = getattr(respuesta, "renderer_context", None) or {}
        decision = getattr(contexto.get("request"), "decision_authz", None)
        if decision is None:
            return respuesta
        respuesta["X-Authz-Permitido"] = "1" if decision.allow else "0"
        respuesta["X-Authz-Regla"] = _limpio(decision.rule_id)
        respuesta["X-Authz-Version"] = _limpio(decision.rule_ver)
        obligaciones = ",".join(_limpio(o) for o in decision.obligations if _limpio(o))
        if obligaciones:
            respuesta["X-Authz-Obligaciones"] = obligaciones
        return respuesta

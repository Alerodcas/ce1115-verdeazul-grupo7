"""Punto de aplicación de la política (PEP).

Parte 1, "Dónde vive la decisión de autorización": la decisión vive en el
servidor, en un solo punto, y deniega por omisión. Ocultar un botón en la
interfaz no es un control.

`DenyAll` es el permiso por omisión de todo el proyecto (ver REST_FRAMEWORK en
config/settings.py). Una vista que no declare nada, no responde. Eso es
deliberado: si alguien agrega una vista y se le olvida el control de acceso, la
vista queda cerrada en vez de abierta.

Dueño del archivo: Kevin.
"""

from __future__ import annotations

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from .pdp import DecisionInput, decidir


class DenyAll(BasePermission):
    """Permiso por omisión: no. Se sobreescribe explícitamente en cada vista."""

    message = "No autorizado."

    def has_permission(self, request, view) -> bool:
        return False


class PermitePorMatriz(BasePermission):
    """Consulta al PDP con la celda (rol × objeto × acción) de la matriz.

    La vista declara qué objeto y qué acción representa:

        class MedicionAprobarView(APIView):
            permission_classes = [PermitePorMatriz]
            objeto_tipo = "Medicion"
            accion = "Approve"

    y opcionalmente implementa `construir_atributos(request, obj)` para las
    celdas condicionadas (C1–C6, S1, S2). Esos atributos SIEMPRE se leen de la
    base de datos, nunca del cuerpo de la petición.
    """

    def has_permission(self, request, view) -> bool:
        if not request.user.is_authenticated:
            return False
        decision = self._consultar(request, view, objeto_id=None)
        request.decision_authz = decision
        return decision.allow

    def has_object_permission(self, request, view, obj) -> bool:
        decision = self._consultar(request, view, objeto_id=str(getattr(obj, "pk", "")), obj=obj)
        request.decision_authz = decision
        if not decision.allow:
            # TODO(Daniel): emitir AUTHZ.DENY en la bitácora antes de responder.
            raise PermissionDenied(detail="No autorizado.")
        return True

    @staticmethod
    def _consultar(request, view, objeto_id, obj=None):
        atributos = {}
        constructor = getattr(view, "construir_atributos", None)
        if callable(constructor):
            atributos = constructor(request, obj)

        entrada = DecisionInput(
            actor=str(request.user.pk),
            roles=_roles_vigentes(request.user),
            rol_activo=request.session.get("rol_activo", ""),
            accion=getattr(view, "accion", ""),
            objeto_tipo=getattr(view, "objeto_tipo", ""),
            objeto_id=objeto_id,
            atributos=atributos,
        )
        return decidir(entrada)


def _roles_vigentes(user) -> list[str]:
    """Roles leídos de la base en cada petición, no copiados a la sesión.

    Parte 1, "Cambio de privilegios": así una baja o un cambio de rol vale de
    inmediato, sin esperar a que la sesión expire.
    """
    return sorted(user.groups.values_list("name", flat=True))

"""Atributos que la política necesita, **leídos de la base de datos**.

Nada de aquí sale del cuerpo de la petición: del cliente solo se toma el
identificador del objeto sobre el que se pregunta, y los hechos sobre ese objeto
(estado, autor, período abierto...) se consultan. Si el identificador no existe o
no se entiende, los atributos quedan en valores que deniegan.
"""

from __future__ import annotations

import time
from datetime import timedelta

from django.utils import timezone

from auditoria.models import Bitacora

from .models import Cuenta, Enmienda, Finca, Medicion, Periodo

VENTANA_MFA_MINUTOS = 5


def mfa_reciente(request, minutos: int = VENTANA_MFA_MINUTOS) -> bool:
    """¿La persona pasó el segundo factor hace poco?

    El segundo factor todavía no está implementado: esta función lee
    `session["mfa_verificado_en"]` (segundos epoch), que debe fijar el flujo de
    MFA cuando exista. Mientras tanto devuelve False y las celdas que exigen MFA
    (C2, C4) quedan cerradas, que es el lado seguro.
    """
    sello = request.session.get("mfa_verificado_en")
    return isinstance(sello, (int, float)) and time.time() - sello <= minutos * 60


def a_entero(valor) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def fincas_leidas_24h(usuario) -> int:
    """Fincas distintas que esta persona leyó en las últimas 24 h (C5), según la bitácora."""
    desde = timezone.now() - timedelta(hours=24)
    return (
        Bitacora.objects.filter(
            actor=str(usuario.pk),
            accion="Read",
            objeto_tipo="Finca",
            resultado=Bitacora.Resultado.EXITO,
            ocurrido_en__gte=desde,
        )
        .values("objeto_id")
        .distinct()
        .count()
    )


def atributos_finca(request, finca: Finca | None) -> dict:
    usuario = request.user
    return {
        "finca_asignada": bool(finca and finca.tecnicos.filter(pk=usuario.pk).exists()),
        "es_propietario": bool(finca and finca.propietario_id == usuario.pk),
        "fincas_leidas_24h": fincas_leidas_24h(usuario),
        "estado_objeto": "activa" if finca and finca.activa else "inactiva",
    }


def atributos_medicion(request, medicion: Medicion | None, *, finca=None, periodo=None) -> dict:
    """Para una medición existente, o para una por crear (finca y período dados)."""
    usuario = request.user
    if medicion is not None:
        finca, periodo = medicion.finca, medicion.periodo
    return {
        "finca_asignada": bool(finca and finca.tecnicos.filter(pk=usuario.pk).exists()),
        "es_propietario": bool(finca and finca.propietario_id == usuario.pk),
        "periodo_abierto": bool(periodo and periodo.abierto),
        "estado_objeto": medicion.estado if medicion else Medicion.Estado.BORRADOR,
        "es_autor": True if medicion is None else medicion.creada_por_id == usuario.pk,
        "fue_editor": bool(
            medicion and medicion.editores.filter(pk=usuario.pk).exists()
        ),
        "mfa_reciente": mfa_reciente(request),
    }


def atributos_periodo(request, periodo: Periodo | None) -> dict:
    return {"estado_objeto": "abierto" if periodo and periodo.abierto else "cerrado"}


def finca_o_none(pk) -> Finca | None:
    pk = a_entero(pk)
    return Finca.objects.filter(pk=pk).first() if pk is not None else None


def periodo_o_none(pk) -> Periodo | None:
    pk = a_entero(pk)
    return Periodo.objects.filter(pk=pk).first() if pk is not None else None


def medicion_o_none(pk) -> Medicion | None:
    pk = a_entero(pk)
    return Medicion.objects.select_related("finca", "periodo").filter(pk=pk).first() if pk is not None else None


def atributos_enmienda(request, enmienda: Enmienda | None, medicion: Medicion | None) -> dict:
    """Regla C4. `solicitante` permite a la política exigir que quien autoriza sea otra persona."""
    usuario = request.user
    base = atributos_medicion(request, medicion)
    base.update(
        estado_objeto=enmienda.estado if enmienda else Enmienda.Estado.SOLICITADA,
        es_autor=enmienda is None or enmienda.solicitante_id == usuario.pk,
        solicitante=str(enmienda.solicitante_id) if enmienda else str(usuario.pk),
    )
    return base


def atributos_cuenta(request, cuenta: Cuenta | None) -> dict:
    """Regla C6."""
    usuario = request.user
    return {
        "estado_objeto": cuenta.estado if cuenta else Cuenta.Estado.SOLICITADA,
        "es_autor": cuenta is None or cuenta.solicitante_id == usuario.pk,
        "solicitante": str(cuenta.solicitante_id) if cuenta else str(usuario.pk),
        "mfa_reciente": mfa_reciente(request),
    }

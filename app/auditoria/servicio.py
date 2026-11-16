"""API de la bitácora: `registrar` y `verificar_cadena`.

Uso desde una vista, haciendo que la acción y su registro sean atómicos
(falla cerrada: si la bitácora no escribe, la acción tampoco ocurre):

    with transaction.atomic():
        medicion.estado = "aprobada"; medicion.save()
        registrar(request, accion="Approve", objeto=medicion,
                  resultado="exito", decision=request.decision_authz)

Para una denegación o un fallo se registra antes de responder; si registrar
levanta `ErrorBitacora`, la respuesta sigue siendo una negativa.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timezone as dt_timezone
from dataclasses import dataclass

from django.db import connection, transaction
from django.utils import timezone

from .models import GENESIS, Bitacora, ErrorBitacora

_CLAVE_BLOQUEO = 7_150_001  # pg_advisory_xact_lock: serializa la escritura en Postgres
_PROHIBIDAS = ("password", "contrasena", "token", "secret", "clave", "cookie", "authorization")


def _canonico(campos: dict) -> bytes:
    return json.dumps(campos, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _campos_firmados(e: Bitacora) -> dict:
    return {
        "ocurrido_en": e.ocurrido_en.astimezone(dt_timezone.utc).isoformat(),
        "actor": e.actor,
        "rol_activo": e.rol_activo,
        "accion": e.accion,
        "objeto_tipo": e.objeto_tipo,
        "objeto_id": e.objeto_id,
        "resultado": e.resultado,
        "rule_id": e.rule_id,
        "rule_ver": e.rule_ver,
        "motivo": e.motivo,
        "ip": e.ip or "",
        "detalle": e.detalle,
    }


def calcular_hash(e: Bitacora) -> str:
    return hashlib.sha256(e.hash_previo.encode() + b"|" + _canonico(_campos_firmados(e))).hexdigest()


def _validar_detalle(detalle: dict) -> None:
    def revisar(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if any(p in str(k).lower() for p in _PROHIBIDAS):
                    raise ErrorBitacora(f"El detalle no puede incluir «{k}»: parece un secreto.")
                revisar(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                revisar(v)

    revisar(detalle)


def _ip(request) -> str | None:
    if request is None:
        return None
    # Detrás de Cloud Run el balanceador reescribe X-Forwarded-For (DESVIACIONES D-01):
    # la última dirección es la que añadió Google, las anteriores las controla el cliente.
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if reenviada:
        return reenviada.split(",")[-1].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def registrar(
    request=None,
    *,
    accion: str,
    resultado: str,
    objeto=None,
    objeto_tipo: str = "",
    objeto_id: str = "",
    decision=None,
    motivo: str = "",
    detalle: dict | None = None,
    actor: str | None = None,
) -> Bitacora:
    """Escribe una entrada. Levanta `ErrorBitacora` si no puede: nunca se traga el error."""
    if resultado not in Bitacora.Resultado.values:
        raise ErrorBitacora(f"Resultado desconocido: {resultado!r}")
    detalle = detalle or {}
    _validar_detalle(detalle)

    user = getattr(request, "user", None)
    if actor is None:
        actor = str(user.pk) if user is not None and user.is_authenticated else "anonimo"
    if objeto is not None:
        objeto_tipo = objeto_tipo or type(objeto).__name__
        objeto_id = objeto_id or str(objeto.pk or "")
    session = getattr(request, "session", None)

    try:
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_advisory_xact_lock(%s)", [_CLAVE_BLOQUEO])
            ultima = Bitacora.objects.order_by("-id").first()
            entrada = Bitacora(
                ocurrido_en=timezone.now(),
                actor=actor,
                rol_activo=(session.get("rol_activo", "") if session is not None else ""),
                accion=accion,
                objeto_tipo=objeto_tipo,
                objeto_id=objeto_id,
                resultado=resultado,
                rule_id=getattr(decision, "rule_id", "") if decision else "",
                rule_ver=getattr(decision, "rule_ver", "") if decision else "",
                motivo=(motivo or (getattr(decision, "reason", "") if decision else ""))[:255],
                ip=_ip(request),
                detalle=detalle,
                hash_previo=ultima.hash if ultima else GENESIS,
            )
            entrada.hash = calcular_hash(entrada)
            entrada.save(force_insert=True)
            return entrada
    except ErrorBitacora:
        raise
    except Exception as exc:  # cualquier fallo de base: se propaga como fallo cerrado
        raise ErrorBitacora("No se pudo escribir en la bitácora.") from exc


@dataclass(frozen=True)
class ResultadoVerificacion:
    ok: bool
    revisadas: int
    primera_rota: int | None = None
    motivo: str = ""


def verificar_cadena() -> ResultadoVerificacion:
    """Recorre la bitácora entera y recalcula la cadena. Detecta alteraciones y
    filas faltantes, pero no que alguien recalcule todo (ver D-03)."""
    esperado = GENESIS
    n = 0
    for e in Bitacora.objects.order_by("id").iterator(chunk_size=500):
        n += 1
        if e.hash_previo != esperado:
            return ResultadoVerificacion(False, n, e.pk, "hash_previo no coincide: falta o se reordenó una entrada")
        if calcular_hash(e) != e.hash:
            return ResultadoVerificacion(False, n, e.pk, "el contenido no coincide con su hash")
        esperado = e.hash
    return ResultadoVerificacion(True, n)

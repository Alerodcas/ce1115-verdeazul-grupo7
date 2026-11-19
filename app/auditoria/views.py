"""Consulta de la bitácora: solo lectura (matriz: Auditor externo y Gerencia, `Read`).

No hay ninguna vista que escriba o borre: la bitácora solo la escribe
`servicio.registrar`, desde el código que ejecuta cada acción. Consultarla también
queda registrado: quien mira la bitácora deja su propio rastro.
"""

from __future__ import annotations

from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from negocio.views import VistaNegocio

from .models import Bitacora
from .serializers import BitacoraSerializer
from .servicio import verificar_cadena

LIMITE_POR_OMISION = 50
LIMITE_MAXIMO = 200
FILTROS_EXACTOS = ("actor", "accion", "objeto_tipo", "objeto_id", "rule_id")


class BitacoraBase(VistaNegocio):
    objeto_tipo = "Bitacora"
    accion = "Read"

    def construir_atributos(self, request, obj):
        return {}


def _entero(request, nombre, defecto, minimo, maximo=None):
    crudo = request.query_params.get(nombre)
    if crudo is None:
        return defecto
    try:
        valor = int(crudo)
    except ValueError:
        raise ValidationError({nombre: "Debe ser un entero."}) from None
    if valor < minimo or (maximo is not None and valor > maximo):
        raise ValidationError({nombre: "Fuera de rango."})
    return valor


def _fecha(request, nombre):
    crudo = request.query_params.get(nombre)
    if crudo is None:
        return None
    fecha = parse_datetime(crudo)
    if fecha is None or fecha.tzinfo is None:
        raise ValidationError({nombre: "Use ISO 8601 con zona horaria, p. ej. 2026-11-16T00:00:00Z."})
    return fecha


class BitacoraListaView(BitacoraBase):
    """Más reciente primero. Filtros exactos, rango de fechas y paginación acotada."""

    def get(self, request):
        qs = Bitacora.objects.order_by("-id")
        filtros = {}
        for campo in FILTROS_EXACTOS:
            if campo in request.query_params:
                filtros[campo] = request.query_params[campo]
        resultado = request.query_params.get("resultado")
        if resultado is not None:
            if resultado not in Bitacora.Resultado.values:
                raise ValidationError({"resultado": f"Use uno de {Bitacora.Resultado.values}."})
            filtros["resultado"] = resultado
        if (desde := _fecha(request, "desde")) is not None:
            filtros["ocurrido_en__gte"] = desde
        if (hasta := _fecha(request, "hasta")) is not None:
            filtros["ocurrido_en__lt"] = hasta
        qs = qs.filter(**filtros)

        limite = _entero(request, "limite", LIMITE_POR_OMISION, 1, LIMITE_MAXIMO)
        desplazamiento = _entero(request, "desplazamiento", 0, 0)
        total = qs.count()
        pagina = list(qs[desplazamiento:desplazamiento + limite])

        self.registrar_exito(request, None, detalle={"consulta": filtros_legibles(filtros), "devueltas": len(pagina)})
        return Response({
            "total": total, "limite": limite, "desplazamiento": desplazamiento,
            "resultados": BitacoraSerializer(pagina, many=True).data,
        })


class BitacoraVerificarView(BitacoraBase):
    """Recalcula la cadena de hashes. 200 si está íntegra, 409 si no."""

    def get(self, request):
        r = verificar_cadena()
        # La consulta se registra después de verificar: así no entra en lo verificado.
        self.registrar_exito(request, None, detalle={"verificacion": "ok" if r.ok else "rota"})
        cuerpo = {"ok": r.ok, "revisadas": r.revisadas, "primera_rota": r.primera_rota, "motivo": r.motivo}
        return Response(cuerpo, status=status.HTTP_200_OK if r.ok else status.HTTP_409_CONFLICT)


def filtros_legibles(filtros: dict) -> dict:
    """Los filtros tal como se pidieron, en texto, para dejarlos en la entrada."""
    return {k: str(v) for k, v in filtros.items()}

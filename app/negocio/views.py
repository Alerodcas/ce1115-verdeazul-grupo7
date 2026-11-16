"""Vistas de negocio: Finca, Periodo y Medición.

Todas pasan por el PEP (`PermitePorMatriz`). Tres reglas que se repiten:

* Los atributos de la política salen de la base (`atributos.py`).
* Toda acción que cambia datos se ejecuta junto con su entrada de bitácora en una
  misma transacción: si la bitácora no escribe, la acción tampoco ocurre y la
  respuesta es 503 (falla cerrada).
* Toda denegación se registra antes de responder, sin tocar `authz/`.

Lo que **no** está aquí todavía: Enmienda, Certificado (emisión: Luis) y Cuenta.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from auditoria.models import ErrorBitacora
from auditoria.servicio import registrar
from authz.permissions import PermitePorMatriz

from . import atributos as attrs
from .models import Finca, Medicion, Periodo
from .serializers import (
    FincaActualizarSerializer,
    FincaSerializer,
    MedicionActualizarSerializer,
    MedicionSerializer,
    PeriodoSerializer,
)

logger = logging.getLogger(__name__)

EDITABLES = (Medicion.Estado.BORRADOR, Medicion.Estado.DEVUELTA)


def _conflicto(detalle: str) -> Response:
    return Response({"detail": detalle}, status=status.HTTP_409_CONFLICT)


class VistaNegocio(APIView):
    permission_classes = [PermitePorMatriz]
    objeto_tipo = ""
    accion = ""
    modelo = None  # para las vistas de detalle
    acciones_por_metodo: dict[str, str] = {}  # si la acción depende del método HTTP

    def initial(self, request, *args, **kwargs):
        # La acción tiene que estar fijada antes de que el PEP pregunte.
        self.accion = self.acciones_por_metodo.get(request.method.lower(), self.accion)
        super().initial(request, *args, **kwargs)

    # -- el objeto sobre el que se pregunta, resuelto desde la URL -----------
    def objeto_actual(self):
        """None si la ruta no lleva pk o el objeto no existe (la política deniega)."""
        if self.modelo is None or "pk" not in self.kwargs:
            return None
        if not hasattr(self, "_objeto"):
            self._objeto = self.queryset_visible().filter(pk=self.kwargs["pk"]).first()
        return self._objeto

    def queryset_visible(self):
        return self.modelo.objects.all()

    def obtener(self, request):
        obj = self.objeto_actual()
        if obj is None:
            raise Http404
        self.check_object_permissions(request, obj)
        return obj

    # -- bitácora ---------------------------------------------------------------
    def permission_denied(self, request, message=None, code=None):
        obj = self.objeto_actual() if self.modelo else None
        try:
            registrar(
                request, accion=self.accion, resultado="denegado",
                objeto_tipo=self.objeto_tipo, objeto_id=str(obj.pk) if obj else "",
                decision=getattr(request, "decision_authz", None),
            )
        except ErrorBitacora:
            logger.exception("No se pudo registrar una denegación; se deniega igual.")
        super().permission_denied(request, message=message, code=code)

    def registrar_exito(self, request, obj, **extra):
        return registrar(
            request, accion=self.accion, resultado="exito", objeto=obj,
            objeto_tipo=self.objeto_tipo, decision=getattr(request, "decision_authz", None),
            **extra,
        )

    def handle_exception(self, exc):
        if isinstance(exc, ErrorBitacora):
            logger.error("Bitácora no disponible: %s", exc)
            return Response(
                {"detail": "Bitácora no disponible; la operación no se realizó."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return super().handle_exception(exc)


# ============================== Finca ========================================
class FincaBase(VistaNegocio):
    objeto_tipo = "Finca"
    modelo = Finca

    def queryset_visible(self):
        """S1 y S2: cada rol ve solo las fincas que le corresponden."""
        rol, u = self.request.session.get("rol_activo", ""), self.request.user
        qs = Finca.objects.all()
        if rol == "Tecnico de campo":
            return qs.filter(tecnicos=u)
        if rol == "Dueno de finca":
            return qs.filter(propietario=u)
        return qs

    def construir_atributos(self, request, obj):
        return attrs.atributos_finca(request, obj or self.objeto_actual())


class FincaListaView(FincaBase):
    accion = "Read"

    def get(self, request):
        return Response(FincaSerializer(self.queryset_visible().order_by("id"), many=True).data)


class FincaCrearView(FincaBase):
    accion = "Create"

    def post(self, request):
        ser = FincaSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            finca = ser.save()
            self.registrar_exito(request, finca)
        return Response(FincaSerializer(finca).data, status=status.HTTP_201_CREATED)


class FincaDetalleView(FincaBase):
    acciones_por_metodo = {"get": "Read", "patch": "Update"}

    def get(self, request, pk):
        finca = self.obtener(request)
        with transaction.atomic():
            self.registrar_exito(request, finca)  # alimenta el umbral C5
        return Response(FincaSerializer(finca).data)

    def patch(self, request, pk):
        finca = self.obtener(request)
        ser = FincaActualizarSerializer(finca, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            ser.save()
            self.registrar_exito(request, finca)
        return Response(ser.data)


class FincaDesactivarView(FincaBase):
    accion = "Deactivate"

    def post(self, request, pk):
        finca = self.obtener(request)
        with transaction.atomic():
            finca.activa = False
            finca.save(update_fields=["activa"])
            self.registrar_exito(request, finca)
        return Response(FincaSerializer(finca).data)


# ============================== Período ======================================
class PeriodoBase(VistaNegocio):
    objeto_tipo = "Periodo"
    modelo = Periodo

    def construir_atributos(self, request, obj):
        return attrs.atributos_periodo(request, obj or self.objeto_actual())


class PeriodoListaView(PeriodoBase):
    accion = "Read"

    def get(self, request):
        return Response(PeriodoSerializer(Periodo.objects.order_by("-inicio"), many=True).data)


class _PeriodoCambiaEstado(PeriodoBase):
    abrir: bool

    def post(self, request, pk):
        periodo = self.obtener(request)
        if periodo.abierto == self.abrir:
            return _conflicto("El período ya está en ese estado.")
        with transaction.atomic():
            periodo.abierto = self.abrir
            periodo.save(update_fields=["abierto"])
            self.registrar_exito(request, periodo)
        return Response(PeriodoSerializer(periodo).data)


class PeriodoAbrirView(_PeriodoCambiaEstado):
    accion, abrir = "Open", True


class PeriodoCerrarView(_PeriodoCambiaEstado):
    accion, abrir = "Close", False


# ============================== Medición =====================================
class MedicionBase(VistaNegocio):
    objeto_tipo = "Medicion"
    modelo = Medicion

    def queryset_visible(self):
        rol, u = self.request.session.get("rol_activo", ""), self.request.user
        qs = Medicion.objects.select_related("finca", "periodo")
        if rol == "Tecnico de campo":
            return qs.filter(finca__tecnicos=u)
        if rol == "Dueno de finca":
            return qs.filter(finca__propietario=u)
        return qs

    def construir_atributos(self, request, obj):
        obj = obj or self.objeto_actual()
        if obj is None and request.method == "POST" and "pk" not in self.kwargs:
            # Por crear: del cuerpo solo se toman los identificadores; los hechos
            # (asignación, período abierto) se consultan.
            return attrs.atributos_medicion(
                request, None,
                finca=attrs.finca_o_none(request.data.get("finca")),
                periodo=attrs.periodo_o_none(request.data.get("periodo")),
            )
        return attrs.atributos_medicion(request, obj)


class MedicionListaView(MedicionBase):
    accion = "Read"

    def get(self, request):
        return Response(MedicionSerializer(self.queryset_visible().order_by("id"), many=True).data)


class MedicionCrearView(MedicionBase):
    accion = "Create"

    def post(self, request):
        ser = MedicionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            medicion = ser.save(creada_por=request.user)
            self.registrar_exito(request, medicion)
        return Response(MedicionSerializer(medicion).data, status=status.HTTP_201_CREATED)


class MedicionDetalleView(MedicionBase):
    acciones_por_metodo = {"get": "Read", "patch": "Update"}

    def get(self, request, pk):
        return Response(MedicionSerializer(self.obtener(request)).data)

    def patch(self, request, pk):
        medicion = self.obtener(request)
        if medicion.estado not in EDITABLES:
            return _conflicto("Solo se edita una medición en borrador o devuelta.")
        ser = MedicionActualizarSerializer(medicion, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            ser.save()
            medicion.editores.add(request.user)  # base de la regla C2
            self.registrar_exito(request, medicion)
        return Response(ser.data)


class _MedicionTransicion(MedicionBase):
    """Cambia el estado de la medición. Las transiciones válidas se fijan aquí."""

    desde: tuple[str, ...]
    hacia: str

    def post(self, request, pk):
        medicion = self.obtener(request)
        if medicion.estado not in self.desde:
            return _conflicto(f"No se puede pasar de «{medicion.estado}» a «{self.hacia}».")
        anterior = medicion.estado
        with transaction.atomic():
            medicion.estado = self.hacia
            medicion.save(update_fields=["estado", "actualizada_en"])
            self.registrar_exito(request, medicion, detalle={"de": anterior, "a": self.hacia})
        return Response(MedicionSerializer(medicion).data)


class MedicionEnviarView(_MedicionTransicion):
    accion, desde, hacia = "Update", EDITABLES, Medicion.Estado.ENVIADA


class MedicionAprobarView(_MedicionTransicion):
    accion, desde, hacia = "Approve", (Medicion.Estado.ENVIADA,), Medicion.Estado.APROBADA


class MedicionDevolverView(_MedicionTransicion):
    accion, desde, hacia = "Return", (Medicion.Estado.ENVIADA,), Medicion.Estado.DEVUELTA

"""Vistas de negocio: Finca, Periodo y Medición.

Todas pasan por el PEP (`PermitePorMatriz`). Tres reglas que se repiten:

* Los atributos de la política salen de la base (`atributos.py`).
* Toda acción que cambia datos se ejecuta junto con su entrada de bitácora en una
  misma transacción: si la bitácora no escribe, la acción tampoco ocurre y la
  respuesta es 503 (falla cerrada).
* Toda denegación se registra antes de responder, sin tocar `authz/`.

Lo que **no** está aquí: la emisión de Certificado (Luis).
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from auditoria.models import ErrorBitacora
from auditoria.servicio import registrar
from authz.permissions import PermitePorMatriz

from . import atributos as attrs
from .models import Cuenta, Enmienda, Finca, Medicion, Periodo
from .serializers import (
    CuentaSerializer,
    EnmiendaSerializer,
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

    @staticmethod
    def bloquear(obj):
        """Relee la fila con bloqueo: el estado se comprueba sobre lo que hay de verdad."""
        return type(obj).objects.select_for_update().get(pk=obj.pk)

    def denegar(self, request, obj, motivo: str) -> Response:
        """Una regla de negocio (separación de funciones) que se trata como denegación."""
        try:
            registrar(
                request, accion=self.accion, resultado="denegado", objeto=obj,
                objeto_tipo=self.objeto_tipo, motivo=motivo,
                decision=getattr(request, "decision_authz", None),
            )
        except ErrorBitacora:
            logger.exception("No se pudo registrar una denegación; se deniega igual.")
        return Response({"detail": motivo}, status=status.HTTP_403_FORBIDDEN)

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
        with transaction.atomic():
            medicion = self.bloquear(medicion)
            if medicion.estado not in self.desde:
                return _conflicto(f"No se puede pasar de «{medicion.estado}» a «{self.hacia}».")
            anterior = medicion.estado
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


# ============================== Enmienda =====================================
class EnmiendaBase(VistaNegocio):
    objeto_tipo = "Enmienda"
    modelo = Enmienda

    def queryset_visible(self):
        rol, u = self.request.session.get("rol_activo", ""), self.request.user
        qs = Enmienda.objects.select_related("medicion__finca", "medicion__periodo")
        if rol == "Tecnico de campo":
            return qs.filter(medicion__finca__tecnicos=u)
        if rol == "Dueno de finca":
            return qs.filter(medicion__finca__propietario=u)
        return qs

    def construir_atributos(self, request, obj):
        obj = obj or self.objeto_actual()
        if obj is None and request.method == "POST" and "pk" not in self.kwargs:
            return attrs.atributos_enmienda(
                request, None, attrs.medicion_o_none(request.data.get("medicion"))
            )
        return attrs.atributos_enmienda(request, obj, obj.medicion if obj else None)


class EnmiendaListaView(EnmiendaBase):
    accion = "Read"

    def get(self, request):
        return Response(EnmiendaSerializer(self.queryset_visible().order_by("id"), many=True).data)


class EnmiendaDetalleView(EnmiendaBase):
    accion = "Read"

    def get(self, request, pk):
        return Response(EnmiendaSerializer(self.obtener(request)).data)


class EnmiendaCrearView(EnmiendaBase):
    """C4: el técnico pide corregir una medición ya aprobada. No la toca: solo pide."""

    accion = "Create"

    def post(self, request):
        ser = EnmiendaSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            medicion = self.bloquear(ser.validated_data["medicion"])
            if medicion.estado != Medicion.Estado.APROBADA:
                return _conflicto("Solo se enmienda una medición aprobada.")
            if medicion.enmiendas.filter(estado=Enmienda.Estado.SOLICITADA).exists():
                return _conflicto("Ya hay una enmienda pendiente para esta medición.")
            if hasattr(medicion, "reemplazada_por"):
                return _conflicto("Esta medición ya fue reemplazada por una versión nueva.")
            enmienda = ser.save(solicitante=request.user)
            self.registrar_exito(request, enmienda)
        return Response(EnmiendaSerializer(enmienda).data, status=status.HTTP_201_CREATED)


class _EnmiendaResuelve(EnmiendaBase):
    """Autorizar o rechazar. Quien solicitó no resuelve su propia enmienda."""

    accion = "Authorize"

    def post(self, request, pk):
        enmienda = self.obtener(request)
        if enmienda.solicitante_id == request.user.pk:
            return self.denegar(request, enmienda, "Quien solicita una enmienda no la autoriza.")
        with transaction.atomic():
            enmienda = self.bloquear(enmienda)
            if enmienda.estado != Enmienda.Estado.SOLICITADA:
                return _conflicto(f"La enmienda ya está «{enmienda.estado}».")
            return self.resolver(request, enmienda)

    def resolver(self, request, enmienda):
        raise NotImplementedError


class EnmiendaAutorizarView(_EnmiendaResuelve):
    def resolver(self, request, enmienda):
        anterior = self.bloquear(enmienda.medicion)
        if anterior.estado != Medicion.Estado.APROBADA or hasattr(anterior, "reemplazada_por"):
            return _conflicto("La medición ya no admite enmienda.")
        # Nunca se sobrescribe: se crea una versión nueva que apunta a la anterior.
        # Queda «enviada» para que un verificador la apruebe de nuevo (C2).
        nueva = Medicion.objects.create(
            finca=anterior.finca, periodo=anterior.periodo, version=anterior.version + 1,
            reemplaza=anterior, valor=enmienda.valor_propuesto, unidad=anterior.unidad,
            estado=Medicion.Estado.ENVIADA, creada_por=enmienda.solicitante,
        )
        enmienda.autorizante = request.user
        enmienda.estado = Enmienda.Estado.APLICADA
        enmienda.medicion_nueva = nueva
        enmienda.save()
        self.registrar_exito(
            request, enmienda,
            detalle={"medicion_anterior": anterior.pk, "medicion_nueva": nueva.pk, "version": nueva.version},
        )
        return Response(EnmiendaSerializer(enmienda).data)


class EnmiendaRechazarView(_EnmiendaResuelve):
    def resolver(self, request, enmienda):
        enmienda.autorizante = request.user
        enmienda.estado = Enmienda.Estado.RECHAZADA
        enmienda.save()
        self.registrar_exito(request, enmienda, detalle={"decision": "rechazada"})
        return Response(EnmiendaSerializer(enmienda).data)


# ============================== Cuenta =======================================
class CuentaBase(VistaNegocio):
    """Gestión de cuentas (C6): solicitud escrita → aprobación → ejecución por otra persona."""

    objeto_tipo = "Cuenta"
    modelo = Cuenta

    def construir_atributos(self, request, obj):
        return attrs.atributos_cuenta(request, obj or self.objeto_actual())


class CuentaListaView(CuentaBase):
    accion = "Read"

    def get(self, request):
        return Response(CuentaSerializer(Cuenta.objects.order_by("id"), many=True).data)


class CuentaDetalleView(CuentaBase):
    accion = "Read"

    def get(self, request, pk):
        return Response(CuentaSerializer(self.obtener(request)).data)


class CuentaCrearView(CuentaBase):
    accion = "Create"

    def post(self, request):
        ser = CuentaSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            cuenta = ser.save(solicitante=request.user)
            self.registrar_exito(request, cuenta, detalle={"tipo": cuenta.tipo})
        return Response(CuentaSerializer(cuenta).data, status=status.HTTP_201_CREATED)


class CuentaAprobarView(CuentaBase):
    accion = "Approve"

    def post(self, request, pk):
        cuenta = self.obtener(request)
        if cuenta.usuario_id == request.user.pk:
            return self.denegar(request, cuenta, "Nadie aprueba cambios sobre su propia cuenta.")
        with transaction.atomic():
            cuenta = self.bloquear(cuenta)
            if cuenta.estado != Cuenta.Estado.SOLICITADA:
                return _conflicto(f"La solicitud ya está «{cuenta.estado}».")
            cuenta.aprobador = request.user
            cuenta.estado = Cuenta.Estado.AUTORIZADA
            cuenta.save()
            self.registrar_exito(request, cuenta, detalle={"tipo": cuenta.tipo})
        return Response(CuentaSerializer(cuenta).data)


class CuentaEjecutarView(CuentaBase):
    """Aplica el cambio. Update si asigna un rol, Deactivate si da de baja."""

    def initial(self, request, *args, **kwargs):
        cuenta = Cuenta.objects.filter(pk=kwargs.get("pk")).first()
        desactiva = cuenta is not None and cuenta.tipo == Cuenta.Tipo.DESACTIVAR
        self.accion = "Deactivate" if desactiva else "Update"
        super().initial(request, *args, **kwargs)

    def post(self, request, pk):
        cuenta = self.obtener(request)
        if request.user.pk in (cuenta.aprobador_id, cuenta.usuario_id):
            return self.denegar(
                request, cuenta,
                "Quien ejecuta debe ser distinto del aprobador y de la persona afectada.",
            )
        with transaction.atomic():
            cuenta = self.bloquear(cuenta)
            if cuenta.estado != Cuenta.Estado.AUTORIZADA:
                return _conflicto("Solo se ejecuta una solicitud autorizada.")
            afectado = get_user_model().objects.select_for_update().get(pk=cuenta.usuario_id)
            if cuenta.tipo == Cuenta.Tipo.DESACTIVAR:
                afectado.is_active = False
                afectado.save(update_fields=["is_active"])
            else:
                grupo = Group.objects.filter(name=cuenta.rol_solicitado).first()
                if grupo is None:
                    return _conflicto("El rol pedido no existe en el sistema.")
                afectado.groups.add(grupo)
            cuenta.ejecutor = request.user
            cuenta.estado = Cuenta.Estado.EJECUTADA
            cuenta.save()
            self.registrar_exito(
                request, cuenta, detalle={"tipo": cuenta.tipo, "rol": cuenta.rol_solicitado},
            )
        return Response(CuentaSerializer(cuenta).data)

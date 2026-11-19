"""Vistas delgadas de la interfaz.

Lo único que hacen estas vistas es: iniciar y cerrar sesión, fijar el rol activo,
confirmar el segundo factor y entregar páginas. Las páginas no traen datos del
negocio: el navegador los pide a la API con la cookie de sesión, y ahí decide el
PEP. Ninguna regla de la matriz vive aquí.
"""

from __future__ import annotations

import logging
import time

from django.contrib.auth import get_user_model, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from auditoria.models import ErrorBitacora
from auditoria.servicio import registrar
from negocio.atributos import VENTANA_MFA_MINUTOS

from . import totp
from .navegacion import PANTALLAS, ROL_POR_VALOR, ROLES_CON_DIRECTORIO, guia, menu, roles_de

logger = logging.getLogger(__name__)

ROL_SESION = "rol_activo"  # la clave que leen authz/permissions.py, negocio y auditoria
MFA_SESION = "mfa_verificado_en"  # la clave que lee negocio/atributos.py
MFA_ULTIMO_PASO = "mfa_ultimo_paso"  # para no aceptar dos veces el mismo código
MFA_FALLOS = "mfa_fallos"
MFA_MAX_FALLOS = 5

# Códigos de evento de sesión en la bitácora. El proyecto usa «AUTH.LOGIN» en las
# pruebas de auditoria; los demás siguen esa forma.
EVENTO_INGRESO = "AUTH.LOGIN"
EVENTO_SALIDA = "AUTH.LOGOUT"
EVENTO_CAMBIO_ROL = "AUTH.ROLE_CHANGE"
EVENTO_MFA = "AUTH.MFA"


def _siguiente_seguro(request, defecto: str) -> str:
    destino = request.POST.get("next") or request.GET.get("next") or ""
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return destino
    return defecto


def _inicio_del_rol(rol: str) -> str:
    propias, _ = menu(rol)
    clave = propias[0].clave if propias else "mediciones"
    return reverse("interfaz:pantalla", args=[clave])


def _registrar_o_avisar(request, **campos) -> bool:
    """Registra en la bitácora. False si no pudo (quien llama decide si falla cerrado)."""
    try:
        registrar(request, **campos)
        return True
    except ErrorBitacora:
        logger.exception("No se pudo registrar %s en la bitácora.", campos.get("accion"))
        return False


# ============================== Sesión =======================================
AVISOS_INGRESO = {
    "mfa": "Hubo demasiados códigos incorrectos y la sesión se cerró. Entre de nuevo para seguir.",
    "sesion": "La sesión terminó por inactividad. Entre de nuevo para seguir donde estaba.",
}


class FormularioIngreso(AuthenticationForm):
    error_messages = {
        "invalid_login": "El usuario y la contraseña no coinciden. Revise los dos datos e "
                         "intente de nuevo.",
        "inactive": "Esta cuenta está desactivada. Si cree que es un error, pida a "
                    "Administración que lo revise.",
    }


class Entrar(LoginView):
    template_name = "interfaz/entrar.html"
    authentication_form = FormularioIngreso
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["aviso"] = AVISOS_INGRESO.get(self.request.GET.get("aviso", ""), "")
        return ctx

    def form_valid(self, form):
        respuesta = super().form_valid(form)  # login() ya rota el identificador de sesión
        # Una sesión nueva empieza sin rol y sin segundo factor: se eligen de nuevo.
        for clave in (ROL_SESION, MFA_SESION, MFA_ULTIMO_PASO, MFA_FALLOS):
            self.request.session.pop(clave, None)
        if not _registrar_o_avisar(
            self.request, accion=EVENTO_INGRESO, resultado="exito", objeto_tipo="Sesion"
        ):
            logout(self.request)  # falla cerrada: sin constancia no hay sesión
            form.add_error(None, "No se pudo dejar constancia del ingreso, así que la sesión "
                                 "no se abrió. Intente de nuevo en unos minutos.")
            return self.form_invalid(form, registrar_fallo=False)
        return respuesta

    def form_invalid(self, form, registrar_fallo=True):
        if registrar_fallo:
            usuario = str(form.data.get("username", ""))[:64]
            _registrar_o_avisar(
                self.request, accion=EVENTO_INGRESO, resultado="fallo",
                objeto_tipo="Sesion", detalle={"usuario": usuario},
            )
        return super().form_invalid(form)


class Salir(LogoutView):
    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            _registrar_o_avisar(request, accion=EVENTO_SALIDA, resultado="exito", objeto_tipo="Sesion")
        return super().post(request, *args, **kwargs)


def fijar_rol(request, rol: str) -> bool:
    """Escribe el rol activo, lo deja en la bitácora y rota el identificador de sesión.

    Rotar en cada cambio de privilegio lo exige el diseño de la Parte 1. Si la
    bitácora no escribe, el rol no cambia (falla cerrada).
    """
    anterior = request.session.get(ROL_SESION, "")
    if anterior == rol:
        return True
    request.session[ROL_SESION] = rol
    if not _registrar_o_avisar(
        request, accion=EVENTO_CAMBIO_ROL, resultado="exito", objeto_tipo="Sesion",
        detalle={"de": anterior, "a": rol},
    ):
        if anterior:
            request.session[ROL_SESION] = anterior
        else:
            request.session.pop(ROL_SESION, None)
        return False
    request.session.cycle_key()
    return True


class ElegirRol(LoginRequiredMixin, View):
    """Lista solo los grupos a los que la persona pertenece de verdad."""

    plantilla = "interfaz/rol.html"

    def get(self, request):
        roles = roles_de(request.user)
        if len(roles) == 1 and "cambiar" not in request.GET:
            return self._aplicar(request, roles[0].valor, roles)
        return self._pantalla(request, roles)

    def post(self, request):
        roles = roles_de(request.user)
        elegido = request.POST.get("rol", "")
        if elegido not in {r.valor for r in roles}:
            return self._pantalla(request, roles, error="Ese rol no está asignado a su cuenta. "
                                                        "Elija uno de la lista.", estado=400)
        return self._aplicar(request, elegido, roles)

    def _aplicar(self, request, rol, roles):
        if not fijar_rol(request, rol):
            return self._pantalla(request, roles, estado=503, error=(
                "No se pudo dejar constancia del cambio de rol, así que el rol no cambió. "
                "Intente de nuevo en unos minutos."))
        return redirect(_siguiente_seguro(request, _inicio_del_rol(rol)))

    def _pantalla(self, request, roles, error="", estado=200):
        return render(request, self.plantilla, {
            "roles": roles,
            "rol_actual": request.session.get(ROL_SESION, ""),
            "error": error,
            "next": _siguiente_seguro(request, ""),
        }, status=estado)


# ============================== Segundo factor ===============================
def _mfa_restante(request) -> int:
    """Segundos que le quedan al segundo factor; 0 si no hay o venció."""
    sello = request.session.get(MFA_SESION)
    if not isinstance(sello, (int, float)):
        return 0
    return max(0, int(sello + VENTANA_MFA_MINUTOS * 60 - time.time()))


class SegundoFactor(LoginRequiredMixin, View):
    plantilla = "interfaz/segundo_factor.html"

    def get(self, request):
        return self._pantalla(request)

    def post(self, request):
        sesion = request.session
        paso = totp.verificar(request.user, request.POST.get("codigo", ""))
        if paso is None or paso <= sesion.get(MFA_ULTIMO_PASO, -1):
            fallos = sesion.get(MFA_FALLOS, 0) + 1
            sesion[MFA_FALLOS] = fallos
            _registrar_o_avisar(request, accion=EVENTO_MFA, resultado="fallo", objeto_tipo="Sesion",
                                detalle={"intento": fallos})
            if fallos >= MFA_MAX_FALLOS:
                logout(request)
                return redirect(f"{reverse('interfaz:entrar')}?aviso=mfa")
            return self._pantalla(request, error=(
                "El código no coincide o ya se usó. Espere al siguiente código de la "
                f"aplicación e intente de nuevo. Quedan {MFA_MAX_FALLOS - fallos} intentos."),
                estado=400)
        sesion[MFA_SESION] = time.time()
        sesion[MFA_ULTIMO_PASO] = paso
        sesion[MFA_FALLOS] = 0
        if not _registrar_o_avisar(request, accion=EVENTO_MFA, resultado="exito", objeto_tipo="Sesion"):
            for clave in (MFA_SESION, MFA_ULTIMO_PASO):
                sesion.pop(clave, None)
            return self._pantalla(request, estado=503, error=(
                "No se pudo dejar constancia del segundo factor, así que no quedó confirmado. "
                "Intente de nuevo en unos minutos."))
        sesion.cycle_key()  # cambio de privilegio: se rota el identificador
        rol = sesion.get(ROL_SESION, "")
        return redirect(_siguiente_seguro(request, _inicio_del_rol(rol) if rol else reverse("interfaz:rol")))

    def _pantalla(self, request, error="", estado=200):
        return render(request, self.plantilla, {
            "error": error,
            "restante": _mfa_restante(request),
            "ventana": VENTANA_MFA_MINUTOS,
            "next": _siguiente_seguro(request, ""),
        }, status=estado)


# ============================== Pantallas del registro =======================
class PantallaRegistro(LoginRequiredMixin, TemplateView):
    """Entrega el armazón de una pantalla. Los datos llegan después, por la API."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.pantalla = PANTALLAS.get(kwargs.get("pantalla", ""))
        if self.pantalla is None:
            raise Http404
        # Sin rol, o con un rol que ya no tiene asignado: a elegir. Esto ordena el
        # flujo de la interfaz; quien concede o niega cada acción sigue siendo el PEP.
        if not _rol_vigente(request):
            return redirect(f"{reverse('interfaz:rol')}?next={request.path}")
        return super().dispatch(request, *args, **kwargs)

    def get_template_names(self):
        return [f"interfaz/pantallas/{self.pantalla.clave}.html"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rol = self.request.session[ROL_SESION]
        propias, resto = menu(rol)
        restante = _mfa_restante(self.request)
        ctx.update(
            pantalla=self.pantalla,
            rol=ROL_POR_VALOR[rol],
            otros_roles=len(roles_de(self.request.user)) > 1,
            guia=guia(rol, self.pantalla.clave),
            en_alcance=self.pantalla in propias,
            usa_directorio=rol in ROLES_CON_DIRECTORIO,
            menu_propio=propias,
            menu_resto=resto,
            mfa_restante=restante,
            mfa_minutos=-(-restante // 60),  # redondeo hacia arriba
        )
        return ctx


def _rol_vigente(request) -> str:
    """El rol activo si la persona todavía lo tiene asignado; si no, cadena vacía."""
    rol = request.session.get(ROL_SESION, "")
    return rol if rol in {r.valor for r in roles_de(request.user)} else ""


@require_GET
def directorio(request):
    """Números y nombres de usuario de las cuentas activas, para mostrar personas.

    Solo existe para que la interfaz escriba «demo_tecnico» donde la API devuelve «1».
    No es un objeto de la matriz ni da acceso a nada: entrega id y username, y nunca
    correo, contraseña, grupos ni banderas. Exige sesión, un rol activo vigente y un rol
    de ROLES_CON_DIRECTORIO; los demás reciben 403 y la interfaz sigue mostrando «#id».
    """
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Inicie sesión."}, status=403)
    rol = _rol_vigente(request)
    if not rol:
        return JsonResponse({"detail": "Elija un rol activo."}, status=403)
    if rol not in ROLES_CON_DIRECTORIO:
        return JsonResponse({"detail": "Este rol no usa el directorio de personas."}, status=403)
    filas = list(
        get_user_model().objects.filter(is_active=True).order_by("username").values("id", "username")
    )
    respuesta = JsonResponse(filas, safe=False)
    respuesta["Cache-Control"] = "no-store"
    return respuesta


def inicio(request):
    if not request.user.is_authenticated:
        return redirect("interfaz:entrar")
    rol = request.session.get(ROL_SESION, "")
    return redirect(_inicio_del_rol(rol) if rol else reverse("interfaz:rol"))

"""Pruebas de la interfaz: ingreso, rol activo, segundo factor y la decisión visible.

El PDP se sustituye por un doble que anota la entrada (como en negocio.tests_vistas).
Las clases «ConOpaReal» repiten lo esencial contra el OPA de verdad y se saltan
solas si no hay uno en OPA_URL.
"""

import json
import re
import shutil
import subprocess
import time
from datetime import date
from pathlib import Path
from unittest import mock, skipUnless

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings

from auditoria.models import Bitacora
from authz.pdp import Decision
from negocio.models import ROLES, Finca, Medicion, Periodo

from . import totp
from .navegacion import ALCANCE, PANTALLAS, ROL_POR_VALOR, ROLES_CON_DIRECTORIO, guia
from .views import EVENTO_CAMBIO_ROL, EVENTO_INGRESO, MFA_SESION

CLAVE = "Clave-de-prueba-2026"

# Las pruebas no corren collectstatic: sin manifiesto, {% static %} usa el almacén simple.
SIN_MANIFIESTO = override_settings(STORAGES={
    **settings.STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})


def _hay_opa() -> bool:
    try:
        return requests.get(f"{settings.OPA_URL}/health", timeout=0.5).ok
    except requests.RequestException:
        return False


class PDPDoble:
    def __init__(self, allow=True):
        self.allow, self.entradas = allow, []

    def __call__(self, entrada):
        self.entradas.append(entrada)
        return Decision(allow=self.allow, rule_id="T1", rule_ver="9", reason="doble")


@SIN_MANIFIESTO
class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.grupos = {r: Group.objects.create(name=r) for r in ROLES}
        U = get_user_model()
        cls.doble = U.objects.create_user("doble", password=CLAVE)  # técnico y verificador
        cls.doble.groups.add(cls.grupos["Tecnico de campo"], cls.grupos["Verificador"])
        cls.solo = U.objects.create_user("solo", password=CLAVE)  # solo auditor
        cls.solo.groups.add(cls.grupos["Auditor externo"])
        cls.dueno = U.objects.create_user("dueno", password=CLAVE)
        cls.finca = Finca.objects.create(nombre="F", area_ha=1, propietario=cls.dueno)
        cls.finca.tecnicos.add(cls.doble)
        cls.periodo = Periodo.objects.create(
            etiqueta="P", inicio=date(2026, 1, 1), fin=date(2026, 12, 31), abierto=True)

    def doble_pdp(self, allow=True):
        self.pdp = PDPDoble(allow)
        p = mock.patch("authz.permissions.decidir", self.pdp)
        p.start()
        self.addCleanup(p.stop)
        return self.pdp

    def cliente(self, usuario, rol=None, mfa=False):
        c = Client()
        c.force_login(usuario)
        s = c.session
        if rol is not None:
            s["rol_activo"] = rol
        if mfa:
            s[MFA_SESION] = time.time()
        s.save()
        return c


# ============================== sin rol activo ===============================
class SinRolActivoTest(Base):
    def test_la_api_niega_a_quien_no_eligio_rol(self):
        pdp = self.doble_pdp(allow=False)
        r = self.cliente(self.doble).get("/api/mediciones/")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(pdp.entradas[-1].rol_activo, "")
        self.assertEqual(r["X-Authz-Permitido"], "0")

    def test_las_pantallas_mandan_a_elegir_rol(self):
        r = self.cliente(self.doble).get("/registro/mediciones/")
        self.assertRedirects(r, "/rol/?next=/registro/mediciones/", fetch_redirect_response=False)

    def test_un_rol_que_ya_no_tiene_no_vale_en_la_interfaz(self):
        r = self.cliente(self.doble, rol="Gerencia de Certificacion").get("/registro/mediciones/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("/rol/"))


@skipUnless(_hay_opa(), "no hay un OPA en OPA_URL")
class SinRolActivoConOpaRealTest(Base):
    def test_sin_rol_la_politica_niega_por_omision(self):
        r = self.cliente(self.doble).get("/api/mediciones/")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r["X-Authz-Regla"], "DENY_DEFAULT")


# ============================== elegir rol ===================================
class ElegirRolTest(Base):
    def test_lista_solo_los_roles_de_la_persona(self):
        r = self.cliente(self.doble).get("/rol/")
        self.assertEqual(r.status_code, 200)
        valores = [x.valor for x in r.context["roles"]]
        self.assertEqual(valores, ["Tecnico de campo", "Verificador"])

    def test_elegir_rol_lo_fija_en_la_sesion_y_rota_la_llave(self):
        c = self.cliente(self.doble)
        antes = c.cookies[settings.SESSION_COOKIE_NAME].value
        r = c.post("/rol/", {"rol": "Verificador"})
        self.assertEqual(r.status_code, 302)
        despues = c.cookies[settings.SESSION_COOKIE_NAME].value
        self.assertNotEqual(antes, despues)
        self.assertEqual(c.session["rol_activo"], "Verificador")
        e = Bitacora.objects.filter(accion=EVENTO_CAMBIO_ROL).get()
        self.assertEqual((e.actor, e.rol_activo, e.detalle), (str(self.doble.pk), "Verificador",
                                                              {"de": "", "a": "Verificador"}))

    def test_cambiar_de_rol_vuelve_a_rotar_y_deja_rastro(self):
        c = self.cliente(self.doble)
        c.post("/rol/", {"rol": "Verificador"})
        antes = c.cookies[settings.SESSION_COOKIE_NAME].value
        c.post("/rol/", {"rol": "Tecnico de campo"})
        self.assertNotEqual(antes, c.cookies[settings.SESSION_COOKIE_NAME].value)
        self.assertEqual(c.session["rol_activo"], "Tecnico de campo")
        self.assertEqual(Bitacora.objects.filter(accion=EVENTO_CAMBIO_ROL).count(), 2)

    def test_no_se_puede_elegir_un_rol_ajeno(self):
        c = self.cliente(self.doble)
        r = c.post("/rol/", {"rol": "Gerencia de Certificacion"})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("rol_activo", c.session)
        self.assertFalse(Bitacora.objects.filter(accion=EVENTO_CAMBIO_ROL).exists())

    def test_con_un_solo_rol_se_salta_la_pantalla_pero_se_fija(self):
        c = self.cliente(self.solo)
        r = c.get("/rol/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.session["rol_activo"], "Auditor externo")
        self.assertTrue(Bitacora.objects.filter(accion=EVENTO_CAMBIO_ROL).exists())

    def test_si_la_bitacora_falla_el_rol_no_cambia(self):
        from auditoria.models import ErrorBitacora
        c = self.cliente(self.doble)
        with mock.patch("interfaz.views.registrar", side_effect=ErrorBitacora("x")):
            r = c.post("/rol/", {"rol": "Verificador"})
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("rol_activo", c.session)

    def test_el_siguiente_externo_se_ignora(self):
        r = self.cliente(self.doble).post("/rol/", {"rol": "Verificador", "next": "https://malo.example/"})
        self.assertEqual(r["Location"], "/registro/mediciones/")


class IngresoTest(Base):
    def test_entrar_lleva_a_elegir_rol_y_queda_en_la_bitacora(self):
        r = Client().post("/entrar/", {"username": "doble", "password": CLAVE})
        self.assertRedirects(r, "/rol/", fetch_redirect_response=False)
        self.assertTrue(Bitacora.objects.filter(accion=EVENTO_INGRESO, resultado="exito").exists())

    def test_un_ingreso_fallido_queda_en_la_bitacora(self):
        r = Client().post("/entrar/", {"username": "doble", "password": "otra-cosa-cualquiera"})
        self.assertEqual(r.status_code, 200)
        e = Bitacora.objects.get(accion=EVENTO_INGRESO)
        self.assertEqual((e.resultado, e.actor, e.detalle), ("fallo", "anonimo", {"usuario": "doble"}))

    def test_la_pagina_de_ingreso_trae_token_csrf(self):
        self.assertContains(Client().get("/entrar/"), 'name="csrfmiddlewaretoken"')


# ============================== separación de funciones (C2) =================
class VerificadorNoApruebaLoSuyoTest(Base):
    def setUp(self):
        self.medicion = Medicion.objects.create(
            finca=self.finca, periodo=self.periodo, valor=5, creada_por=self.doble,
            estado=Medicion.Estado.ENVIADA)

    def test_el_pep_recibe_que_es_el_autor_y_niega(self):
        pdp = self.doble_pdp(allow=False)
        c = self.cliente(self.doble, rol="Verificador", mfa=True)
        r = c.post(f"/api/mediciones/{self.medicion.pk}/aprobar/")
        self.assertEqual(r.status_code, 403)
        entrada = pdp.entradas[-1]
        self.assertEqual((entrada.rol_activo, entrada.accion), ("Verificador", "Approve"))
        self.assertIs(entrada.atributos["es_autor"], True)
        self.medicion.refresh_from_db()
        self.assertEqual(self.medicion.estado, Medicion.Estado.ENVIADA)


@skipUnless(_hay_opa(), "no hay un OPA en OPA_URL")
class VerificadorNoApruebaLoSuyoConOpaRealTest(Base):
    def test_c2_niega_al_autor_aunque_tenga_segundo_factor(self):
        m = Medicion.objects.create(finca=self.finca, periodo=self.periodo, valor=5,
                                    creada_por=self.doble, estado=Medicion.Estado.ENVIADA)
        r = self.cliente(self.doble, rol="Verificador", mfa=True).post(f"/api/mediciones/{m.pk}/aprobar/")
        self.assertEqual(r.status_code, 403)
        self.assertEqual((r["X-Authz-Regla"], r["X-Authz-Version"]), ("C2", "1"))
        m.refresh_from_db()
        self.assertEqual(m.estado, Medicion.Estado.ENVIADA)

    def test_otro_verificador_con_segundo_factor_si_aprueba(self):
        otro = get_user_model().objects.create_user("verif", password=CLAVE)
        otro.groups.add(self.grupos["Verificador"])
        m = Medicion.objects.create(finca=self.finca, periodo=self.periodo, valor=5,
                                    creada_por=self.doble, estado=Medicion.Estado.ENVIADA)
        r = self.cliente(otro, rol="Verificador", mfa=True).post(f"/api/mediciones/{m.pk}/aprobar/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["X-Authz-Regla"], "C2")


# ============================== decisión en cabeceras ========================
class DecisionEnCabecerasTest(Base):
    def test_una_respuesta_permitida_lleva_su_regla(self):
        self.doble_pdp(allow=True)
        r = self.cliente(self.doble, rol="Tecnico de campo").get("/api/periodos/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r["X-Authz-Permitido"], r["X-Authz-Regla"], r["X-Authz-Version"]),
                         ("1", "T1", "9"))

    def test_sin_consulta_al_pdp_no_se_agrega_nada(self):
        r = Client().get("/health")
        self.assertNotIn("X-Authz-Regla", r)


# ============================== segundo factor ===============================
class TotpTest(TestCase):
    def test_vector_del_rfc_6238(self):
        clave = b"12345678901234567890"
        self.assertEqual(totp.codigo(clave, 59 // 30, digitos=8), "94287082")
        self.assertEqual(totp.codigo(clave, 1111111109 // 30, digitos=8), "07081804")


class SegundoFactorTest(Base):
    def codigo_actual(self, usuario):
        return totp.codigo(totp.secreto(usuario), totp.paso_actual())

    def test_un_codigo_correcto_fija_el_sello_y_rota_la_sesion(self):
        c = self.cliente(self.doble, rol="Verificador")
        antes = c.cookies[settings.SESSION_COOKIE_NAME].value
        r = c.post("/segundo-factor/", {"codigo": self.codigo_actual(self.doble)})
        self.assertEqual(r.status_code, 302)
        self.assertIn(MFA_SESION, c.session)
        self.assertNotEqual(antes, c.cookies[settings.SESSION_COOKIE_NAME].value)

    def test_un_codigo_incorrecto_no_fija_nada(self):
        c = self.cliente(self.doble, rol="Verificador")
        correcto = self.codigo_actual(self.doble)
        malo = str((int(correcto) + 1) % 10**6).zfill(6)
        r = c.post("/segundo-factor/", {"codigo": malo})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn(MFA_SESION, c.session)

    def test_el_mismo_codigo_no_vale_dos_veces(self):
        c = self.cliente(self.doble, rol="Verificador")
        codigo = self.codigo_actual(self.doble)
        c.post("/segundo-factor/", {"codigo": codigo})
        self.assertEqual(c.post("/segundo-factor/", {"codigo": codigo}).status_code, 400)

    def test_cinco_fallos_cierran_la_sesion(self):
        c = self.cliente(self.doble, rol="Verificador")
        for _ in range(5):
            r = c.post("/segundo-factor/", {"codigo": "000000x"})
        self.assertRedirects(r, "/entrar/?aviso=mfa", fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", c.session)


# ============================== plantillas y navegación ======================
@SIN_MANIFIESTO
class PlantillasTest(TestCase):
    def test_ningun_guion_en_linea(self):
        """La CSP no admite guiones en línea: todo <script> lleva src y no hay on*=."""
        raiz = Path(__file__).parent / "templates"
        for archivo in raiz.rglob("*.html"):
            texto = archivo.read_text(encoding="utf-8")
            for etiqueta in re.findall(r"<script\b[^>]*>", texto):
                self.assertIn("src=", etiqueta, f"{archivo.name}: {etiqueta}")
            self.assertIsNone(re.search(r"\son[a-z]+\s*=", texto), archivo.name)

    def test_la_navegacion_conoce_los_seis_roles(self):
        self.assertEqual(set(ROL_POR_VALOR), set(ROLES))

    def test_las_pantallas_responden_con_rol(self):
        u = get_user_model().objects.create_user("g", password=CLAVE)
        u.groups.add(Group.objects.create(name="Gerencia de Certificacion"))
        c = Client()
        c.force_login(u)
        s = c.session
        s["rol_activo"] = "Gerencia de Certificacion"
        s.save()
        for p in ("mediciones", "fincas", "periodos", "certificados", "enmiendas", "cuentas", "bitacora"):
            r = c.get(f"/registro/{p}/")
            self.assertEqual(r.status_code, 200, p)
            self.assertContains(r, "Gerencia de Certificación")
            self.assertContains(r, "Versión")


    def test_cada_static_apunta_a_un_archivo_que_existe(self):
        """Un {% static %} roto rompe collectstatic y la imagen de Docker."""
        aqui = Path(__file__).parent
        for archivo in (aqui / "templates").rglob("*.html"):
            for ruta in re.findall(r"""{%\s*static\s+['"]([^'"]+)['"]\s*%}""", archivo.read_text(encoding="utf-8")):
                self.assertTrue((aqui / "static" / ruta).is_file(), f"{archivo.name}: {ruta}")


# ============================== ayuda por rol y pantalla =====================
class GuiaTest(TestCase):
    def test_cada_rol_tiene_ayuda_en_cada_pantalla(self):
        for rol in ROL_POR_VALOR:
            for clave in PANTALLAS:
                g = guia(rol, clave)
                self.assertTrue(g.puede and g.no_puede, (rol, clave))

    def test_lo_que_esta_en_alcance_tiene_ayuda_propia(self):
        generica = guia("Rol que no existe", "mediciones")
        for rol, claves in ALCANCE.items():
            for clave in claves:
                self.assertNotEqual(guia(rol, clave), generica, (rol, clave))

    def test_fuera_de_alcance_nombra_la_regla_que_niega(self):
        self.assertIn("DENY_DEFAULT", guia("Tecnico de campo", "bitacora").no_puede)

    def test_certificados_conserva_la_nota_de_que_no_consulta_la_matriz(self):
        for rol in ROL_POR_VALOR:
            self.assertIn("todavía no consulta la matriz", guia(rol, "certificados").no_puede, rol)


# ============================== directorio de personas =======================
@SIN_MANIFIESTO
class DirectorioTest(Base):
    URL = "/registro/directorio/"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        U = get_user_model()
        cls.admin = U.objects.create_user("admin_x", password=CLAVE, email="secreto@ejemplo.org")
        cls.admin.groups.add(cls.grupos["Administrador"])
        cls.dueno.groups.add(cls.grupos["Dueno de finca"])
        cls.inactivo = U.objects.create_user("ya_no_esta", password=CLAVE, is_active=False)

    def test_sin_sesion_se_niega(self):
        r = Client().get(self.URL)
        self.assertEqual(r.status_code, 403)

    def test_sin_rol_activo_se_niega(self):
        r = self.cliente(self.admin).get(self.URL)
        self.assertEqual(r.status_code, 403)

    def test_un_rol_que_ya_no_tiene_no_vale(self):
        r = self.cliente(self.solo, rol="Administrador").get(self.URL)
        self.assertEqual(r.status_code, 403)

    def test_tecnico_y_dueno_no_lo_reciben(self):
        self.assertNotIn("Tecnico de campo", ROLES_CON_DIRECTORIO)
        self.assertNotIn("Dueno de finca", ROLES_CON_DIRECTORIO)
        for usuario, rol in ((self.doble, "Tecnico de campo"), (self.dueno, "Dueno de finca")):
            r = self.cliente(usuario, rol=rol).get(self.URL)
            self.assertEqual(r.status_code, 403, rol)

    def test_entrega_solo_id_y_nombre_de_cuentas_activas(self):
        r = self.cliente(self.admin, rol="Administrador").get(self.URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Cache-Control"], "no-store")
        filas = r.json()
        for f in filas:
            self.assertEqual(set(f), {"id", "username"})
        nombres = {f["username"] for f in filas}
        self.assertIn("admin_x", nombres)
        self.assertNotIn("ya_no_esta", nombres)
        self.assertNotIn("secreto@ejemplo.org", r.content.decode())

    def test_solo_admite_get(self):
        r = self.cliente(self.admin, rol="Administrador").post(self.URL)
        self.assertEqual(r.status_code, 405)

    def test_la_pantalla_anuncia_el_directorio_solo_a_quien_lo_usa(self):
        r = self.cliente(self.admin, rol="Administrador").get("/registro/cuentas/")
        self.assertContains(r, 'data-directorio="/registro/directorio/"')
        r = self.cliente(self.doble, rol="Tecnico de campo").get("/registro/mediciones/")
        self.assertContains(r, 'data-directorio=""')


@SIN_MANIFIESTO
class PantallaGuiaTest(Base):
    def test_la_pantalla_muestra_lo_que_el_rol_puede_y_no_puede(self):
        r = self.cliente(self.doble, rol="Verificador").get("/registro/mediciones/")
        self.assertContains(r, "Qué puede hacer aquí como Verificador")
        self.assertContains(r, guia("Verificador", "mediciones").puede)

    def test_fuera_de_alcance_lo_dice_y_no_oculta_la_pantalla(self):
        r = self.cliente(self.solo, rol="Auditor externo").get("/registro/cuentas/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Esta pantalla está fuera del alcance de Auditor externo")
        self.assertContains(r, "Registrar solicitud")  # el formulario sigue ahí, para probarlo

    def test_cambiar_de_rol_esta_siempre_a_un_clic(self):
        r = self.cliente(self.solo, rol="Auditor externo").get("/registro/bitacora/")
        self.assertContains(r, "Cambiar de rol")


# ============================== consejo tras una negación (registro.js) ======
# Corre el registro.js de verdad en Node, con un documento mínimo. Se salta si no hay
# Node (no es una dependencia del proyecto; los ejecutores de GitHub lo traen).
_ARNES_JS = r"""
const fs = require('fs'), vm = require('vm');
// Con «node -e» no hay nombre de guion en argv: los argumentos empiezan en 1.
const [archivo, casosJson] = process.argv.slice(1);
const fuente = fs.readFileSync(archivo, 'utf8');
const salida = JSON.parse(casosJson).map(function (caso) {
  const body = { dataset: { usuarioId: '7', usuario: 'prueba', rol: 'Tecnico de campo',
                            mfaRestante: String(caso.mfa ? 300 : 0), otrosRoles: '' } };
  const ctx = { document: { body: body, querySelector: () => null, getElementById: () => null },
                location: { pathname: '/registro/fincas/' }, Node: function () {},
                setTimeout: setTimeout, setInterval: setInterval };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(fuente, ctx);
  const c = ctx.Registro.interpretar(caso.res, caso.accion || { verbo: 'Probar', exito: 'Hecha' }, []);
  return { tipo: c.tipo, siguiente: c.siguiente || '', enlaceMfa: !!c.enlaceMfa, hechos: c.hechos,
           sistema: !!c.sistema, regla: c.regla || '' };
});
process.stdout.write(JSON.stringify(salida));
"""


def _negada(regla, obligaciones=()):
    return {"ok": False, "estado": 403, "datos": {"detail": ""}, "red": False,
            "decision": {"permitido": False, "regla": regla, "version": "1", "obligaciones": list(obligaciones)}}


@skipUnless(shutil.which("node"), "Node no está instalado")
class ConsejoTrasNegacionTest(TestCase):
    def correr(self, casos):
        archivo = Path(__file__).parent / "static" / "interfaz" / "js" / "registro.js"
        # Sin shell y con argumentos fijos de esta prueba: no hay entrada externa.
        r = subprocess.run([shutil.which("node"), "-e", _ARNES_JS, str(archivo), json.dumps(casos)],  # noqa: S603
                           capture_output=True, text=True, encoding="utf-8", timeout=30, check=True)
        return json.loads(r.stdout)

    def test_c5_sin_obligacion_no_manda_al_segundo_factor(self):
        """Técnico sin la finca asignada: la causa real es S1, el segundo factor no ayuda."""
        (c,) = self.correr([{"res": _negada("C5"), "mfa": False}])
        self.assertFalse(c["enlaceMfa"])
        self.assertNotRegex(c["siguiente"], r"(?i)conf[ií]rmelo|confirme el segundo")
        self.assertIn("S1", c["siguiente"])
        self.assertFalse(any("segundo factor" in h for h in c["hechos"]))

    def test_c5_con_obligacion_y_sin_segundo_factor_si_lo_pide(self):
        (c,) = self.correr([{"res": _negada("C5", ["mfa_reciente", "alerta_frecuencia_c5"]), "mfa": False}])
        self.assertTrue(c["enlaceMfa"])
        self.assertIn("confírmelo", c["siguiente"])

    def test_c5_con_segundo_factor_vigente_no_lo_vuelve_a_pedir(self):
        (c,) = self.correr([{"res": _negada("C5", ["mfa_reciente"]), "mfa": True}])
        self.assertFalse(c["enlaceMfa"])
        self.assertNotIn("confírmelo", c["siguiente"])

    def test_c5_bloqueado_dice_que_el_segundo_factor_no_cambia_nada(self):
        (c,) = self.correr([{"res": _negada("C5", ["alerta_frecuencia_c5"]), "mfa": False}])
        self.assertFalse(c["enlaceMfa"])
        self.assertIn("más de 60", c["siguiente"])

    def test_c2_pide_segundo_factor_solo_si_falta_y_la_decision_lo_exige(self):
        falta, vigente, sin_obligacion = self.correr([
            {"res": _negada("C2", ["mfa_reciente"]), "mfa": False},
            {"res": _negada("C2", ["mfa_reciente"]), "mfa": True},
            {"res": _negada("C2"), "mfa": False},
        ])
        self.assertTrue(falta["enlaceMfa"])
        self.assertIn("confírmelo", falta["siguiente"])
        for c in (vigente, sin_obligacion):
            self.assertFalse(c["enlaceMfa"])
            self.assertNotIn("confírmelo", c["siguiente"])
            self.assertIn("otro verificador", c["siguiente"])

    def test_ninguna_regla_manda_al_segundo_factor_sin_la_obligacion(self):
        reglas = ["DENY_DEFAULT", "MATRIZ_SIMPLE", "FAIL_CLOSED", "C1", "C2", "C3", "C4", "C5", "C6", "S1", "S2"]
        resultados = self.correr([{"res": _negada(r), "mfa": False} for r in reglas])
        for regla, c in zip(reglas, resultados, strict=True):
            self.assertFalse(c["enlaceMfa"], regla)
            self.assertNotRegex(c["siguiente"], r"(?i)conf[ií]rmelo|confirme el segundo", regla)
            self.assertEqual(c["regla"], regla)  # la regla se sigue mostrando

    def test_los_rechazos_del_sistema_no_parecen_de_la_matriz(self):
        unicidad = {"ok": False, "estado": 400, "red": False, "decision": None,
                    "datos": {"non_field_errors": ["Ya hay una medición de esa finca en ese período."]}}
        estado = {"ok": False, "estado": 409, "red": False, "decision": None,
                  "datos": {"detail": "Solo se ejecuta una solicitud autorizada."}}
        vista = {"ok": False, "estado": 403, "red": False, "datos": {"detail": "Nadie aprueba cambios sobre su propia cuenta."},
                 "decision": {"permitido": True, "regla": "C6", "version": "1", "obligaciones": []}}
        a, b, v, m = self.correr([
            {"res": unicidad, "mfa": False},
            {"res": estado, "mfa": False, "accion": {"verbo": "Ejecutar #4", "exito": "Ejecutada", "sinCambio": "Pida a Gerencia."}},
            {"res": vista, "mfa": False},
            {"res": _negada("C2", ["mfa_reciente"]), "mfa": True},
        ])
        for c in (a, b, v):
            self.assertEqual(c["tipo"], "sistema")
            self.assertTrue(c["sistema"])
        self.assertEqual(b["siguiente"], "Pida a Gerencia.")
        self.assertEqual(v["regla"], "C6")  # la regla de la matriz sigue a la vista
        self.assertEqual((m["tipo"], m["sistema"]), ("denegada", False))

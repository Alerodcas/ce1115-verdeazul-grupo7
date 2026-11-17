"""Las vistas contra el OPA de verdad, con las reglas de `opa/policies/`.

Las demás pruebas usan un doble del PDP. Estas sirven para comprobar que lo que
las vistas mandan (atributos leídos de la base) es lo que la política espera, de
punta a punta y por rol. Se saltan solas si no hay un OPA en OPA_URL:

    docker run -d --rm -p 127.0.0.1:8181:8181 -v "$PWD/opa/policies:/policies:ro" \\
        openpolicyagent/opa:1.0.0-static run --server --addr=0.0.0.0:8181 /policies
    python manage.py test negocio.tests_opa_real

Responsable: Daniel.
"""

import time
from datetime import date
from unittest import skipUnless

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from auditoria.models import Bitacora
from auditoria.servicio import verificar_cadena

from .models import Enmienda, Finca, Medicion, Periodo


def _hay_opa() -> bool:
    try:
        return requests.get(f"{settings.OPA_URL}/health", timeout=0.5).ok
    except requests.RequestException:
        return False


@skipUnless(_hay_opa(), "no hay un OPA en OPA_URL")
class ConOpaRealTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        U = get_user_model()
        for n in ("tec", "tec2", "verif", "gerente", "admin", "admin2", "aud", "dueno", "nuevo"):
            setattr(cls, n, U.objects.create(username=n))
        cls.finca = Finca.objects.create(nombre="A", area_ha=1, propietario=cls.dueno)
        cls.finca.tecnicos.add(cls.tec)
        cls.abierto = Periodo.objects.create(etiqueta="P1", inicio=date(2026, 1, 1), fin=date(2026, 3, 31), abierto=True)
        cls.cerrado = Periodo.objects.create(etiqueta="P0", inicio=date(2025, 1, 1), fin=date(2025, 3, 31))
        Group.objects.create(name="Verificador")

    def c(self, usuario, rol, mfa=False):
        cl = APIClient()
        cl.force_login(usuario)
        s = cl.session
        s["rol_activo"] = rol
        if mfa:
            s["mfa_verificado_en"] = time.time()
        s.save()
        return cl

    def nueva(self, **kw):
        datos = {"finca": self.finca.pk, "periodo": self.abierto.pk, "valor": "5"}
        return self.c(self.tec, "Tecnico de campo").post("/api/mediciones/nueva/", {**datos, **kw}, format="json")

    # -- Medición: C1 y C2 -------------------------------------------------
    def test_c1_tecnico_crea_edita_y_envia_en_periodo_abierto(self):
        r = self.nueva()
        self.assertEqual(r.status_code, 201, r.content)
        pk = r.json()["id"]
        t = self.c(self.tec, "Tecnico de campo")
        self.assertEqual(t.patch(f"/api/mediciones/{pk}/", {"valor": "6"}, format="json").status_code, 200)
        self.assertEqual(t.post(f"/api/mediciones/{pk}/enviar/").status_code, 200)
        self.assertEqual(t.patch(f"/api/mediciones/{pk}/", {"valor": "7"}, format="json").status_code, 403)  # ya enviada

    def test_c1_niega_periodo_cerrado_y_finca_ajena(self):
        self.assertEqual(self.nueva(periodo=self.cerrado.pk).status_code, 403)
        r = self.c(self.tec2, "Tecnico de campo").post(
            "/api/mediciones/nueva/", {"finca": self.finca.pk, "periodo": self.abierto.pk, "valor": "5"}, format="json")
        self.assertEqual(r.status_code, 403)
        denegadas = Bitacora.objects.filter(resultado="denegado", accion="Create")
        self.assertEqual(set(denegadas.values_list("rule_id", flat=True)), {"C1"})

    def test_c2_verificador_aprueba_solo_con_mfa(self):
        pk = self.nueva().json()["id"]
        self.c(self.tec, "Tecnico de campo").post(f"/api/mediciones/{pk}/enviar/")
        sin = self.c(self.verif, "Verificador").post(f"/api/mediciones/{pk}/aprobar/")
        self.assertEqual(sin.status_code, 403)
        con = self.c(self.verif, "Verificador", mfa=True).post(f"/api/mediciones/{pk}/aprobar/")
        self.assertEqual(con.status_code, 200, con.content)
        self.assertEqual(Medicion.objects.get(pk=pk).estado, "aprobada")
        e = Bitacora.objects.filter(accion="Approve")
        self.assertEqual([(x.resultado, x.rule_id) for x in e], [("denegado", "C2"), ("exito", "C2")])

    def test_c2_quien_edito_no_aprueba(self):
        m = Medicion.objects.create(finca=self.finca, periodo=self.abierto, valor=1, estado="enviada", creada_por=self.tec)
        m.editores.add(self.verif)
        r = self.c(self.verif, "Verificador", mfa=True).post(f"/api/mediciones/{m.pk}/aprobar/")
        self.assertEqual(r.status_code, 403)

    # -- Lecturas: S1, S2, C5 ----------------------------------------------
    def test_lecturas_por_rol(self):
        self.assertEqual(self.c(self.tec, "Tecnico de campo").get("/api/fincas/").status_code, 200)
        self.assertEqual(self.c(self.tec, "Tecnico de campo").get(f"/api/fincas/{self.finca.pk}/").status_code, 200)
        self.assertEqual(self.c(self.tec2, "Tecnico de campo").get("/api/fincas/").status_code, 403)  # S1
        self.assertEqual(self.c(self.dueno, "Dueno de finca").get(f"/api/fincas/{self.finca.pk}/").status_code, 200)
        self.assertEqual(self.c(self.dueno, "Dueno de finca").get("/api/mediciones/").status_code, 200)
        self.assertEqual(self.c(self.tec2, "Dueno de finca").get("/api/fincas/").status_code, 403)  # S2: no es propietario

    # -- Enmienda: C4 -------------------------------------------------------
    def _aprobada_cerrada(self):
        return Medicion.objects.create(finca=self.finca, periodo=self.cerrado, valor=5, estado="aprobada", creada_por=self.tec)

    def test_c4_flujo_completo(self):
        m = self._aprobada_cerrada()
        t = self.c(self.tec, "Tecnico de campo")
        sin_motivo = t.post("/api/enmiendas/nueva/", {"medicion": m.pk, "motivo": "  ", "valor_propuesto": "8"}, format="json")
        self.assertEqual(sin_motivo.status_code, 403)
        r = t.post("/api/enmiendas/nueva/", {"medicion": m.pk, "motivo": "error", "valor_propuesto": "8"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        pk = r.json()["id"]
        self.assertEqual(t.get("/api/enmiendas/").status_code, 200)
        propia = self.c(self.tec, "Gerencia de Certificacion").post(f"/api/enmiendas/{pk}/autorizar/")
        self.assertEqual(propia.status_code, 403)  # el solicitante no autoriza
        ok = self.c(self.gerente, "Gerencia de Certificacion").post(f"/api/enmiendas/{pk}/autorizar/")
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(Enmienda.objects.get(pk=pk).medicion_nueva.version, 2)

    def test_c4_no_se_pide_con_el_periodo_abierto(self):
        m = Medicion.objects.create(finca=self.finca, periodo=self.abierto, valor=5, estado="aprobada", creada_por=self.tec)
        r = self.c(self.tec, "Tecnico de campo").post(
            "/api/enmiendas/nueva/", {"medicion": m.pk, "motivo": "x", "valor_propuesto": "8"}, format="json")
        self.assertEqual(r.status_code, 403)

    # -- Cuenta: C6 ---------------------------------------------------------
    def test_c6_flujo_completo(self):
        a = self.c(self.admin, "Administrador")
        datos = {"usuario": self.nuevo.pk, "rol_solicitado": "Verificador", "solicitud": "Oficio 1"}
        self.assertEqual(a.post("/api/cuentas/nueva/", {**datos, "solicitud": " "}, format="json").status_code, 403)
        r = a.post("/api/cuentas/nueva/", datos, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        pk = r.json()["id"]
        # La aprobación es de la Gerencia, no del Administrador.
        self.assertEqual(self.c(self.admin2, "Administrador").post(f"/api/cuentas/{pk}/aprobar/").status_code, 403)
        self.assertEqual(self.c(self.gerente, "Gerencia de Certificacion").post(f"/api/cuentas/{pk}/aprobar/").status_code, 200)
        self.assertEqual(self.c(self.admin2, "Administrador").post(f"/api/cuentas/{pk}/ejecutar/").status_code, 200)
        self.assertTrue(self.nuevo.groups.filter(name="Verificador").exists())

    def test_c6_nadie_se_da_acceso_a_si_mismo(self):
        r = self.c(self.admin, "Administrador").post(
            "/api/cuentas/nueva/", {"usuario": self.admin.pk, "rol_solicitado": "Verificador", "solicitud": "x"}, format="json")
        self.assertEqual(r.status_code, 403)

    # -- Bitácora -----------------------------------------------------------
    def test_bitacora_solo_para_auditor_y_gerencia(self):
        self.assertEqual(self.c(self.aud, "Auditor externo").get("/bitacora/").status_code, 200)
        self.assertEqual(self.c(self.gerente, "Gerencia de Certificacion").get("/bitacora/verificar/").status_code, 200)
        self.assertEqual(self.c(self.tec, "Tecnico de campo").get("/bitacora/").status_code, 403)
        self.assertEqual(self.c(self.admin, "Administrador").get("/bitacora/").status_code, 403)

    def test_la_cadena_queda_integra_despues_de_todo(self):
        self.test_c2_verificador_aprueba_solo_con_mfa()
        self.test_c1_niega_periodo_cerrado_y_finca_ajena()
        self.assertTrue(verificar_cadena().ok)

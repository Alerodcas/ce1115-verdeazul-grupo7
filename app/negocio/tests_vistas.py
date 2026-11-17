"""Pruebas de las vistas de negocio. Responsable: Daniel.

El PDP (OPA) no corre en integración continua: se sustituye por un doble que
anota la entrada que recibió. Lo que se prueba aquí es lo que sí es de las
vistas: de dónde salen los atributos, que la bitácora acompañe cada acción y que
falle cerrado.
"""

from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from auditoria.models import Bitacora, ErrorBitacora
from auditoria.servicio import verificar_cadena
from authz.pdp import Decision

from .models import Finca, Medicion, Periodo


class PDPDoble:
    """Concede o niega y guarda las entradas que recibió."""

    def __init__(self, allow=True):
        self.allow, self.entradas = allow, []

    def __call__(self, entrada):
        self.entradas.append(entrada)
        return Decision(allow=self.allow, rule_id="T1", rule_ver="9", reason="doble de prueba")


class BaseVistas(TestCase):
    @classmethod
    def setUpTestData(cls):
        U = get_user_model()
        cls.tec, cls.otro, cls.dueno = (U.objects.create(username=n) for n in ("tec", "otro", "dueno"))
        cls.finca = Finca.objects.create(nombre="A", area_ha=1, propietario=cls.dueno)
        cls.ajena = Finca.objects.create(nombre="B", area_ha=1, propietario=cls.dueno)
        cls.finca.tecnicos.add(cls.tec)
        cls.abierto = Periodo.objects.create(etiqueta="P1", inicio=date(2026, 1, 1), fin=date(2026, 3, 31), abierto=True)
        cls.cerrado = Periodo.objects.create(etiqueta="P0", inicio=date(2025, 1, 1), fin=date(2025, 3, 31))

    def cliente(self, usuario, rol="Tecnico de campo", allow=True):
        c = APIClient()
        c.force_login(usuario)
        s = c.session
        s["rol_activo"] = rol
        s.save()
        self.pdp = PDPDoble(allow)
        patcher = mock.patch("authz.permissions.decidir", self.pdp)
        patcher.start()
        self.addCleanup(patcher.stop)
        return c

    def medicion(self, **kw):
        base = dict(finca=self.finca, periodo=self.abierto, valor=5, creada_por=self.tec)
        return Medicion.objects.create(**{**base, **kw})


class BitacoraDeAccesoTest(BaseVistas):
    def test_sin_sesion_se_deniega_y_se_registra(self):
        r = APIClient().get("/api/fincas/")
        self.assertIn(r.status_code, (401, 403))
        e = Bitacora.objects.get()
        self.assertEqual((e.actor, e.resultado, e.accion, e.objeto_tipo), ("anonimo", "denegado", "Read", "Finca"))

    def test_denegacion_del_pdp_queda_con_su_regla(self):
        c = self.cliente(self.tec, allow=False)
        self.assertEqual(c.post(f"/api/mediciones/{self.medicion().pk}/aprobar/").status_code, 403)
        e = Bitacora.objects.get()
        self.assertEqual((e.resultado, e.accion, e.rule_id, e.rule_ver), ("denegado", "Approve", "T1", "9"))

    def test_si_la_bitacora_falla_la_denegacion_sigue_siendo_denegacion(self):
        c = self.cliente(self.tec, allow=False)
        with mock.patch("negocio.views.registrar", side_effect=ErrorBitacora("x")):
            self.assertEqual(c.get("/api/fincas/").status_code, 403)


class AtributosTest(BaseVistas):
    def test_los_atributos_salen_de_la_base_no_del_cuerpo(self):
        c = self.cliente(self.otro)  # no está asignado a la finca
        c.post("/api/mediciones/nueva/", {
            "finca": self.finca.pk, "periodo": self.cerrado.pk, "valor": "3",
            "finca_asignada": True, "periodo_abierto": True, "es_autor": True,
        }, format="json")
        a = self.pdp.entradas[0].atributos
        self.assertFalse(a["finca_asignada"])
        self.assertFalse(a["periodo_abierto"])

    def test_identificador_invalido_cierra(self):
        c = self.cliente(self.tec)
        c.post("/api/mediciones/nueva/", {"finca": "abc", "periodo": None, "valor": "1"}, format="json")
        a = self.pdp.entradas[0].atributos
        self.assertFalse(a["finca_asignada"])
        self.assertFalse(a["periodo_abierto"])

    def test_fue_editor_y_es_autor_se_leen_de_la_medicion(self):
        m = self.medicion(creada_por=self.otro)
        m.editores.add(self.tec)
        c = self.cliente(self.tec, "Verificador")
        c.post(f"/api/mediciones/{m.pk}/aprobar/")
        a = self.pdp.entradas[0].atributos
        self.assertEqual((a["fue_editor"], a["es_autor"], a["estado_objeto"]), (True, False, "borrador"))

    def test_mfa_cerrado_mientras_no_exista_el_flujo(self):
        c = self.cliente(self.tec, "Verificador")
        c.get("/api/mediciones/")
        self.assertFalse(self.pdp.entradas[0].atributos["mfa_reciente"])

    def test_umbral_c5_cuenta_fincas_leidas_en_24h(self):
        c = self.cliente(self.tec)
        c.get(f"/api/fincas/{self.finca.pk}/")
        c.get(f"/api/fincas/{self.finca.pk}/")  # la misma no suma dos veces
        c.get(f"/api/fincas/{self.finca.pk}/")
        self.assertEqual(self.pdp.entradas[-1].atributos["fincas_leidas_24h"], 1)


class MedicionTest(BaseVistas):
    def test_crear_fija_autor_y_estado_en_el_servidor(self):
        c = self.cliente(self.tec)
        r = c.post("/api/mediciones/nueva/", {
            "finca": self.finca.pk, "periodo": self.abierto.pk, "valor": "7.5",
            "estado": "aprobada", "creada_por": self.otro.pk, "version": 9,
        }, format="json")
        self.assertEqual(r.status_code, 201)
        m = Medicion.objects.get()
        self.assertEqual((m.creada_por, m.estado, m.version), (self.tec, "borrador", 1))
        e = Bitacora.objects.get()
        self.assertEqual((e.resultado, e.accion, e.objeto_id, e.rule_id), ("exito", "Create", str(m.pk), "T1"))

    def test_flujo_enviar_y_aprobar_deja_rastro(self):
        m = self.medicion()
        c = self.cliente(self.tec)
        self.assertEqual(c.post(f"/api/mediciones/{m.pk}/enviar/").status_code, 200)
        c = self.cliente(self.otro, "Verificador")
        self.assertEqual(c.post(f"/api/mediciones/{m.pk}/aprobar/").status_code, 200)
        m.refresh_from_db()
        self.assertEqual(m.estado, "aprobada")
        self.assertEqual(list(Bitacora.objects.values_list("accion", flat=True)), ["Update", "Approve"])
        self.assertTrue(verificar_cadena().ok)

    def test_transicion_invalida_es_409_y_no_registra_exito(self):
        m = self.medicion()  # borrador: no se aprueba
        c = self.cliente(self.otro, "Verificador")
        self.assertEqual(c.post(f"/api/mediciones/{m.pk}/aprobar/").status_code, 409)
        self.assertFalse(Bitacora.objects.filter(resultado="exito").exists())

    def test_una_aprobada_no_se_edita(self):
        m = self.medicion(estado="aprobada")
        c = self.cliente(self.tec)
        self.assertEqual(c.patch(f"/api/mediciones/{m.pk}/", {"valor": "1"}, format="json").status_code, 409)

    def test_editar_registra_al_editor(self):
        m = self.medicion()  # el técnico solo edita las suyas
        c = self.cliente(self.tec)
        c.patch(f"/api/mediciones/{m.pk}/", {"valor": "9", "finca": self.ajena.pk}, format="json")
        m.refresh_from_db()
        self.assertEqual((str(m.valor), m.finca_id), ("9.000", self.finca.pk))  # la finca no cambia
        self.assertIn(self.tec, m.editores.all())

    def test_si_la_bitacora_falla_la_accion_no_ocurre(self):
        m = self.medicion(estado="enviada")
        c = self.cliente(self.otro, "Verificador")
        with mock.patch("negocio.views.registrar", side_effect=ErrorBitacora("caida")):
            r = c.post(f"/api/mediciones/{m.pk}/aprobar/")
        self.assertEqual(r.status_code, 503)
        m.refresh_from_db()
        self.assertEqual(m.estado, "enviada")


class VisibilidadTest(BaseVistas):
    def test_tecnico_solo_ve_sus_fincas(self):
        c = self.cliente(self.tec)
        nombres = [f["nombre"] for f in c.get("/api/fincas/").json()]
        self.assertEqual(nombres, ["A"])
        # Aun con un PDP que concede, la consulta ya excluye lo ajeno: 404.
        self.assertEqual(c.get(f"/api/fincas/{self.ajena.pk}/").status_code, 404)

    def test_dueno_solo_ve_lo_propio(self):
        c = self.cliente(self.otro, "Dueno de finca")
        self.assertEqual(c.get("/api/fincas/").json(), [])

    def test_objeto_ajeno_e_inexistente_responden_igual(self):
        c = self.cliente(self.tec)
        ajena = c.get(f"/api/fincas/{self.ajena.pk}/").status_code
        self.assertEqual(ajena, c.get("/api/fincas/99999/").status_code)

    def test_objeto_inexistente_llega_al_pdp_con_atributos_que_deniegan(self):
        c = self.cliente(self.tec, allow=False)
        self.assertEqual(c.get("/api/fincas/99999/").status_code, 403)
        a = self.pdp.entradas[0].atributos
        self.assertEqual((a["finca_asignada"], a["es_propietario"]), (False, False))


class FincaYPeriodoTest(BaseVistas):
    def test_desactivar_no_borra(self):
        c = self.cliente(self.tec, "Administrador")
        self.assertEqual(c.post(f"/api/fincas/{self.finca.pk}/desactivar/").status_code, 200)
        self.finca.refresh_from_db()
        self.assertFalse(self.finca.activa)

    def test_abrir_y_cerrar_periodo(self):
        c = self.cliente(self.tec, "Gerencia de Certificacion")
        self.assertEqual(c.post(f"/api/periodos/{self.cerrado.pk}/abrir/").status_code, 200)
        self.assertEqual(c.post(f"/api/periodos/{self.cerrado.pk}/abrir/").status_code, 409)
        self.assertEqual(c.post(f"/api/periodos/{self.cerrado.pk}/cerrar/").status_code, 200)

    def test_crear_finca_exige_propietario_y_la_registra(self):
        c = self.cliente(self.tec, "Administrador")
        r = c.post("/api/fincas/nueva/", {"nombre": "N", "area_ha": "2", "propietario": self.dueno.pk}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertTrue(Finca.objects.filter(nombre="N", activa=True).exists())
        self.assertEqual(Bitacora.objects.get().accion, "Create")

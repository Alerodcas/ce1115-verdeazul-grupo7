"""Pruebas de la consulta de la bitácora. Responsable: Daniel."""

from datetime import timedelta
from unittest import mock, skipUnless

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from negocio.tests_vistas import PDPDoble

from .models import Bitacora, ErrorBitacora
from .servicio import registrar


class ConsultaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.u = get_user_model().objects.create(username="aud")

    def setUp(self):
        for i in range(5):
            registrar(accion="Read" if i % 2 else "Create", resultado="exito" if i < 4 else "denegado",
                      actor=f"u{i % 2}", objeto_tipo="Finca", objeto_id=str(i))

    def cliente(self, allow=True):
        c = APIClient()
        c.force_login(self.u)
        s = c.session
        s["rol_activo"] = "Auditor externo"
        s.save()
        self.pdp = PDPDoble(allow)
        p = mock.patch("authz.permissions.decidir", self.pdp)
        p.start()
        self.addCleanup(p.stop)
        return c

    def test_pasa_por_el_pep_y_se_deniega_si_el_pdp_niega(self):
        c = self.cliente(allow=False)
        self.assertEqual(c.get("/bitacora/").status_code, 403)
        e = Bitacora.objects.last()
        self.assertEqual((e.resultado, e.accion, e.objeto_tipo), ("denegado", "Read", "Bitacora"))

    def test_sin_sesion_no_se_lee(self):
        self.assertIn(APIClient().get("/bitacora/").status_code, (401, 403))

    def test_lista_lo_mas_reciente_primero_y_pagina(self):
        # Cada consulta agrega su propia entrada (de objeto «Bitacora»), así que se
        # pagina sobre las de «Finca» para que la página 2 no se corra.
        q = {"objeto_tipo": "Finca", "limite": 2}
        r = self.cliente().get("/bitacora/", q).json()
        self.assertEqual((r["total"], r["limite"], len(r["resultados"])), (5, 2, 2))
        ids = [e["id"] for e in r["resultados"]]
        self.assertEqual(ids, sorted(ids, reverse=True))
        r2 = self.cliente().get("/bitacora/", {**q, "desplazamiento": 2}).json()
        self.assertTrue(set(ids).isdisjoint(e["id"] for e in r2["resultados"]))

    def test_filtros(self):
        c = self.cliente()
        self.assertEqual(c.get("/bitacora/", {"resultado": "denegado"}).json()["total"], 1)
        self.assertEqual(c.get("/bitacora/", {"actor": "u0", "accion": "Create"}).json()["total"], 3)
        futuro = (timezone.now() + timedelta(days=1)).isoformat()
        self.assertEqual(c.get("/bitacora/", {"desde": futuro}).json()["total"], 0)

    def test_parametros_invalidos_son_400(self):
        c = self.cliente()
        for q in ({"limite": "abc"}, {"limite": 9999}, {"limite": 0}, {"desplazamiento": -1},
                  {"resultado": "quizas"}, {"desde": "ayer"}, {"desde": "2026-01-01T00:00:00"}):
            self.assertEqual(c.get("/bitacora/", q).status_code, 400, q)

    def test_un_filtro_no_permite_inyectar_campos(self):
        # `hash` no es un filtro admitido: se ignora, no se interpreta como campo.
        r = self.cliente().get("/bitacora/", {"hash__regex": ".*", "ip": "1.1.1.1"}).json()
        self.assertEqual(r["total"], 5)

    def test_consultar_deja_rastro_y_no_escribe_nada_mas(self):
        antes = Bitacora.objects.count()
        self.cliente().get("/bitacora/", {"actor": "u0"})
        self.assertEqual(Bitacora.objects.count(), antes + 1)
        e = Bitacora.objects.last()
        self.assertEqual((e.accion, e.objeto_tipo, e.resultado), ("Read", "Bitacora", "exito"))
        self.assertEqual(e.detalle["consulta"], {"actor": "u0"})

    def test_no_hay_escritura_por_http(self):
        c = self.cliente()
        for metodo in (c.post, c.put, c.patch, c.delete):
            self.assertEqual(metodo("/bitacora/").status_code, 405)

    def test_si_no_se_puede_registrar_la_consulta_no_se_entrega(self):
        c = self.cliente()
        with mock.patch("negocio.views.registrar", side_effect=ErrorBitacora("caida")):
            r = c.get("/bitacora/")
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("resultados", r.json())


class VerificarTest(ConsultaTest):
    def test_cadena_integra(self):
        r = self.cliente().get("/bitacora/verificar/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["ok"], r.json()["revisadas"]), (True, 5))

    @skipUnless(connection.vendor == "sqlite", "quita disparadores de SQLite")
    def test_cadena_rota_es_409(self):
        with connection.cursor() as c:
            c.execute("DROP TRIGGER bitacora_sin_update")
            c.execute("UPDATE auditoria_bitacora SET resultado='fallo' WHERE id=2")
        r = self.cliente().get("/bitacora/verificar/")
        self.assertEqual((r.status_code, r.json()["ok"], r.json()["primera_rota"]), (409, False, 2))

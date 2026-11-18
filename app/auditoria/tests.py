"""Pruebas de la bitácora. Responsable: Daniel."""

from unittest import mock, skipUnless

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import RequestFactory, TestCase

from negocio.models import Finca

from .models import GENESIS, Bitacora, BitacoraInmutable, ErrorBitacora
from .servicio import registrar, verificar_cadena

SQLITE = connection.vendor == "sqlite"


class RegistrarTest(TestCase):
    def test_encadena_las_entradas(self):
        a = registrar(accion="Create", resultado="exito", actor="1")
        b = registrar(accion="Read", resultado="denegado", actor="1")
        self.assertEqual(a.hash_previo, GENESIS)
        self.assertEqual(b.hash_previo, a.hash)
        self.assertTrue(verificar_cadena().ok)

    def test_guarda_regla_y_motivo_del_pdp(self):
        d = mock.Mock(rule_id="C2", rule_ver="3", reason="Fue editor")
        e = registrar(accion="Approve", resultado="denegado", decision=d, actor="7")
        self.assertEqual((e.rule_id, e.rule_ver, e.motivo), ("C2", "3", "Fue editor"))

    def test_registra_al_actor_anonimo(self):
        req = RequestFactory().get("/")
        req.user = mock.Mock(is_authenticated=False)
        self.assertEqual(registrar(req, accion="AUTH.LOGIN", resultado="fallo").actor, "anonimo")

    def test_rechaza_secretos_en_el_detalle(self):
        with self.assertRaises(ErrorBitacora):
            registrar(accion="AUTH.LOGIN", resultado="fallo", detalle={"x": {"password": "a"}})

    def test_resultado_invalido(self):
        with self.assertRaises(ErrorBitacora):
            registrar(accion="Create", resultado="quizas")

    def test_ip_toma_la_ultima_de_x_forwarded_for(self):
        req = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.9")
        req.user = mock.Mock(is_authenticated=False)
        self.assertEqual(registrar(req, accion="Read", resultado="exito").ip, "203.0.113.9")


class FallaCerradaTest(TestCase):
    def test_si_la_bitacora_falla_la_accion_se_revierte(self):
        u = get_user_model().objects.create(username="ana")
        with mock.patch.object(Bitacora, "save", side_effect=RuntimeError("base caida")):
            with self.assertRaises(ErrorBitacora), transaction.atomic():
                Finca.objects.create(nombre="X", area_ha=1, propietario=u)
                registrar(accion="Create", resultado="exito", actor=str(u.pk))
        self.assertEqual(Finca.objects.count(), 0)


class SoloInsercionTest(TestCase):
    def setUp(self):
        self.e = registrar(accion="Create", resultado="exito", actor="1")

    def test_modelo_rechaza_modificar_y_borrar(self):
        self.e.motivo = "otro"
        with self.assertRaises(BitacoraInmutable):
            self.e.save()
        with self.assertRaises(BitacoraInmutable):
            self.e.delete()
        with self.assertRaises(BitacoraInmutable):
            Bitacora.objects.all().update(motivo="x")
        with self.assertRaises(BitacoraInmutable):
            Bitacora.objects.all().delete()

    @skipUnless(SQLITE, "el SQL crudo de la prueba es de SQLite")
    def test_la_base_rechaza_sql_directo(self):
        from django.db import DatabaseError
        for sql in ("UPDATE auditoria_bitacora SET motivo='x'", "DELETE FROM auditoria_bitacora"):
            with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as c:
                c.execute(sql)


@skipUnless(SQLITE, "quita los disparadores de SQLite para simular a un dueño de la base")
class VerificacionTest(TestCase):
    def _sin_disparadores(self):
        with connection.cursor() as c:
            c.execute("DROP TRIGGER bitacora_sin_update")
            c.execute("DROP TRIGGER bitacora_sin_delete")

    def setUp(self):
        self.a, self.b, self.c = (registrar(accion="Read", resultado="exito", actor=str(i)) for i in range(3))
        self._sin_disparadores()

    def test_detecta_contenido_alterado(self):
        with connection.cursor() as c:
            c.execute("UPDATE auditoria_bitacora SET resultado='denegado' WHERE id=%s", [self.b.pk])
        r = verificar_cadena()
        self.assertEqual((r.ok, r.primera_rota), (False, self.b.pk))

    def test_detecta_entrada_borrada(self):
        with connection.cursor() as c:
            c.execute("DELETE FROM auditoria_bitacora WHERE id=%s", [self.b.pk])
        r = verificar_cadena()
        self.assertEqual((r.ok, r.primera_rota), (False, self.c.pk))

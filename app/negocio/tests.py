"""Pruebas de las reglas que viven en la base de datos. Responsable: Daniel."""

from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import (
    Certificado, Cuenta, Enmienda, Finca, Medicion, Periodo, ProtectedOperation,
)


class BaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        U = get_user_model()
        cls.ana, cls.beto, cls.carla = (U.objects.create(username=n) for n in ("ana", "beto", "carla"))
        cls.finca = Finca.objects.create(nombre="La Esperanza", area_ha="12.5", propietario=cls.ana)
        cls.periodo = Periodo.objects.create(etiqueta="2026-T1", inicio=date(2026, 1, 1), fin=date(2026, 3, 31))


class NoSeBorraTest(BaseTest):
    def test_delete_de_instancia(self):
        with self.assertRaises(ProtectedOperation):
            self.finca.delete()

    def test_delete_en_lote(self):
        with self.assertRaises(ProtectedOperation):
            Finca.objects.all().delete()

    def test_no_se_borra_el_usuario_con_fincas(self):
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.ana.delete()


class ReglasTest(BaseTest):
    def _falla(self, fn):
        with self.assertRaises(IntegrityError), transaction.atomic():
            fn()

    def test_periodo_fin_posterior_al_inicio(self):
        self._falla(lambda: Periodo.objects.create(etiqueta="x", inicio=date(2026, 5, 1), fin=date(2026, 5, 1)))

    def test_un_solo_certificado_vigente(self):
        Certificado.objects.create(finca=self.finca, periodo=self.periodo, emitido_por=self.ana)
        self._falla(lambda: Certificado.objects.create(finca=self.finca, periodo=self.periodo, emitido_por=self.ana))

    def test_revocado_permite_uno_nuevo(self):
        c = Certificado.objects.create(finca=self.finca, periodo=self.periodo, emitido_por=self.ana)
        c.estado = Certificado.Estado.REVOCADO
        c.save()
        Certificado.objects.create(finca=self.finca, periodo=self.periodo, emitido_por=self.ana)

    def test_version_de_medicion_unica(self):
        kw = dict(finca=self.finca, periodo=self.periodo, valor=1, creada_por=self.ana)
        Medicion.objects.create(**kw)
        self._falla(lambda: Medicion.objects.create(**kw))

    def test_enmienda_no_se_autoriza_a_si_mismo(self):
        m = Medicion.objects.create(finca=self.finca, periodo=self.periodo, valor=1, creada_por=self.ana)
        self._falla(lambda: Enmienda.objects.create(
            medicion=m, solicitante=self.ana, autorizante=self.ana, motivo="x", valor_propuesto=2))

    def test_cuenta_ejecutor_distinto_de_aprobador(self):
        self._falla(lambda: Cuenta.objects.create(
            usuario=self.carla, rol_solicitado="Verificador", solicitud="x",
            solicitante=self.ana, ejecutor=self.beto, aprobador=self.beto))

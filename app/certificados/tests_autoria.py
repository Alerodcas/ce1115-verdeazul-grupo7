"""Separación de funciones al emitir (regla C3, es_autor): quien creó la medición no
emite su certificado, aunque además tenga el rol de Verificador.

La emisión exige la medición de origen; el servidor comprueba que esté aprobada, que la
finca enviada sea la suya y que quien emite no sea su autor.
"""

import os
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from auditoria.models import Bitacora
from certificados.crypto import generate_key_pair
from certificados.models import Certificado, PeriodoMedida
from certificados.serializers import uuid_de_finca
from negocio.models import Finca, Medicion, Periodo

CLAVE = "Clave-de-prueba-2026"


class EmisionSinAutoriaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        U = get_user_model()
        tecnico = Group.objects.create(name="Tecnico de campo")
        verificador = Group.objects.create(name="Verificador")
        # Técnico y verificador a la vez: el caso que la regla debe frenar.
        cls.doble = U.objects.create_user("doble", password=CLAVE)
        cls.doble.groups.add(tecnico, verificador)
        cls.otro = U.objects.create_user("otro", password=CLAVE)
        cls.otro.groups.add(verificador)
        dueno = U.objects.create_user("dueno", password=CLAVE)

        cls.finca = Finca.objects.create(nombre="F", area_ha=1, propietario=dueno)
        cls.finca.tecnicos.add(cls.doble)
        periodo = Periodo.objects.create(
            etiqueta="P", inicio=date(2026, 1, 1), fin=date(2026, 12, 31), abierto=True)
        cls.medicion = Medicion.objects.create(
            finca=cls.finca, periodo=periodo, valor="10.000",
            estado=Medicion.Estado.APROBADA, creada_por=cls.doble)
        cls.borrador = Medicion.objects.create(
            finca=cls.finca, periodo=periodo, version=2, valor="10.000",
            estado=Medicion.Estado.BORRADOR, creada_por=cls.otro)
        cls.periodo_cert = PeriodoMedida.objects.create(
            name="Período de prueba", year=2026, status="ABIERTO", modified_by=cls.otro)

    def setUp(self):
        privada, _ = generate_key_pair()
        p = mock.patch.dict(os.environ, {"VERDEAZUL_CERT_SIGNING_KEY": privada})
        p.start()
        self.addCleanup(p.stop)

    def emitir(self, usuario, medicion, finca_id=None):
        cliente = APIClient()
        cliente.force_authenticate(usuario)
        datos = {
            "period": str(self.periodo_cert.id),
            "finca_id": finca_id or uuid_de_finca(self.finca.pk),
            "parcela_id": "P-01",
            "tons_co2": "10.00",
        }
        if medicion is not None:
            datos["medicion"] = medicion.pk
        return cliente.post("/certificados/emitir/", datos, format="json")

    def test_el_autor_de_la_medicion_no_emite_su_certificado(self):
        r = self.emitir(self.doble, self.medicion)
        self.assertEqual(r.status_code, 403, r.content)
        self.assertIn("usted creó", r.json()["detail"])
        self.assertFalse(Certificado.objects.exists())

    def test_la_negacion_queda_en_la_bitacora(self):
        self.emitir(self.doble, self.medicion)
        entrada = Bitacora.objects.filter(objeto_tipo="Certificado", resultado="denegado").get()
        self.assertEqual(entrada.accion, "Create")
        self.assertEqual(entrada.actor, str(self.doble.pk))
        self.assertEqual(entrada.objeto_id, str(self.medicion.pk))

    def test_otro_verificador_si_emite(self):
        r = self.emitir(self.otro, self.medicion)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Certificado.objects.get().emitted_by, self.otro)

    def test_sin_medicion_no_se_emite(self):
        r = self.emitir(self.otro, None)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("medicion", r.json())

    def test_la_medicion_tiene_que_estar_aprobada(self):
        r = self.emitir(self.otro, self.borrador)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("medicion", r.json())

    def test_la_finca_tiene_que_ser_la_de_la_medicion(self):
        # Sin esto, bastaría con citar la medición de otro y certificar una finca distinta.
        r = self.emitir(self.otro, self.medicion, finca_id=uuid_de_finca(self.finca.pk + 1))
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("finca_id", r.json())

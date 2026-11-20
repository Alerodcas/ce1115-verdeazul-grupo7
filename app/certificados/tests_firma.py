"""Regresión: un certificado recién emitido se verifica aunque las toneladas sean enteras.

Antes, tons_co2 se firmaba como float (10.0). El navegador hace JSON.parse/stringify y
lo reescribe como 10; al re-serializar, los bytes ya no coincidían con lo firmado y un
certificado intacto se rechazaba. Ahora va firmado como texto con dos decimales.
"""

import json
import os
from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from certificados.crypto import generate_key_pair, verify_sign
from certificados.models import Certificado, PeriodoMedida
from certificados.serializers import uuid_de_finca
from negocio.models import Finca, Medicion, Periodo

CLAVE = "Clave-de-prueba-2026"


def como_el_navegador(datos):
    """Ida y vuelta por JSON con la semántica de JavaScript: un número entero no
    conserva su «.0» (JSON.parse('10.0') es 10 y JSON.stringify(10) es '10')."""
    def numero(texto):
        valor = float(texto)
        return int(valor) if valor.is_integer() else valor
    return json.loads(json.dumps(datos), parse_float=numero)


class FirmaSobreviveAlNavegadorTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        U = get_user_model()
        cls.usuario = U.objects.create_user("emisor", password=CLAVE)
        cls.periodo = PeriodoMedida.objects.create(
            name="Período de prueba", year=2026, status="ABIERTO", modified_by=cls.usuario)
        # La emisión exige una medición aprobada que el emisor no haya creado (C3).
        tecnico = U.objects.create_user("tecnico", password=CLAVE)
        cls.finca = Finca.objects.create(nombre="F", area_ha=1, propietario=tecnico)
        cls.medicion = Medicion.objects.create(
            finca=cls.finca,
            periodo=Periodo.objects.create(
                etiqueta="P", inicio=date(2026, 1, 1), fin=date(2026, 12, 31), abierto=True),
            valor="10.000", estado=Medicion.Estado.APROBADA, creada_por=tecnico)

    def setUp(self):
        privada, _ = generate_key_pair()
        p = mock.patch.dict(os.environ, {"VERDEAZUL_CERT_SIGNING_KEY": privada})
        p.start()
        self.addCleanup(p.stop)
        self.cliente = APIClient()
        self.cliente.force_authenticate(self.usuario)

    def emitir(self, toneladas, parcela):
        r = self.cliente.post("/certificados/emitir/", {
            "medicion": self.medicion.pk,
            "period": str(self.periodo.id),
            "finca_id": uuid_de_finca(self.finca.pk),
            "parcela_id": parcela,
            "tons_co2": toneladas,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def test_toneladas_enteras_verifican_tras_la_ida_y_vuelta(self):
        c = self.emitir("10.00", "P-ENTERA")
        self.assertEqual(c["canonical_data"]["tons_co2"], "10.00")
        datos = como_el_navegador(c["canonical_data"])
        self.assertTrue(verify_sign(datos, c["sign_digital"], c["public_key_pem"]))
        r = self.cliente.post("/certificados/verificar/", {
            "canonical_data": datos, "sign_digital": c["sign_digital"], "public_key_pem": c["public_key_pem"],
        }, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIs(r.json()["valido"], True)

    def test_toneladas_con_decimales_siguen_verificando(self):
        c = self.emitir("12.34", "P-DECIMAL")
        self.assertEqual(c["canonical_data"]["tons_co2"], "12.34")
        datos = como_el_navegador(c["canonical_data"])
        self.assertTrue(verify_sign(datos, c["sign_digital"], c["public_key_pem"]))

    def test_alterar_las_toneladas_sigue_rompiendo_la_firma(self):
        c = self.emitir("10.00", "P-ALTERADA")
        datos = como_el_navegador(c["canonical_data"])
        datos["tons_co2"] = "11.00"
        self.assertFalse(verify_sign(datos, c["sign_digital"], c["public_key_pem"]))

    def test_el_modelo_guarda_el_decimal_como_antes(self):
        c = self.emitir("10.00", "P-MODELO")
        self.assertEqual(Certificado.objects.get(pk=c["id"]).tons_co2, Decimal("10.00"))

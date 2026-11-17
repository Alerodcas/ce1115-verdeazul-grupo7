"""Pruebas del comando de siembra. Responsable: Daniel."""

import io
import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from auditoria.models import Bitacora

from .management.commands.sembrar_demo import USUARIOS
from .models import ROLES, Finca, Medicion, Periodo

CLAVE = "una-clave-de-prueba-larga-93"


def sembrar(*args, clave=CLAVE, confirmar=True):
    # El corredor de pruebas apaga DEBUG, así que por omisión se confirma.
    if confirmar:
        args = (*args, "--confirmar")
    env = {"VERDEAZUL_DEMO_PASSWORD": clave} if clave is not None else {}
    with mock.patch.dict(os.environ, env, clear=False):
        if clave is None:
            os.environ.pop("VERDEAZUL_DEMO_PASSWORD", None)
        out = io.StringIO()
        call_command("sembrar_demo", *args, stdout=out)
        return out.getvalue()


class SiembraTest(TestCase):
    def test_crea_roles_usuarios_finca_y_periodos(self):
        sembrar()
        self.assertEqual(set(Group.objects.values_list("name", flat=True)), set(ROLES))
        U = get_user_model()
        self.assertEqual(U.objects.count(), len(USUARIOS))
        self.assertTrue(U.objects.get(username="demo_verificador").groups.filter(name="Verificador").exists())
        finca = Finca.objects.get()
        self.assertEqual(finca.propietario.username, "demo_dueno")
        self.assertEqual(list(finca.tecnicos.values_list("username", flat=True)), ["demo_tecnico"])
        self.assertEqual(Periodo.objects.filter(abierto=True).count(), 1)
        self.assertEqual(Periodo.objects.filter(abierto=False).count(), 1)

    def test_no_siembra_nada_que_deba_pasar_por_la_bitacora(self):
        sembrar()
        self.assertEqual((Medicion.objects.count(), Bitacora.objects.count()), (0, 0))

    def test_las_cuentas_no_son_staff_ni_superusuario(self):
        sembrar()
        self.assertFalse(get_user_model().objects.filter(is_staff=True).exists())
        self.assertFalse(get_user_model().objects.filter(is_superuser=True).exists())

    def test_la_clave_entra_y_no_se_imprime(self):
        salida = sembrar()
        self.assertNotIn(CLAVE, salida)
        u = get_user_model().objects.get(username="demo_admin")
        self.assertTrue(u.check_password(CLAVE))
        self.assertTrue(u.password.startswith("argon2"))

    def test_es_idempotente_y_no_pisa_claves_existentes(self):
        sembrar()
        sembrar(clave="otra-clave-de-prueba-larga-77")
        self.assertEqual(get_user_model().objects.count(), len(USUARIOS))
        self.assertEqual(Finca.objects.count(), 1)
        self.assertTrue(get_user_model().objects.get(username="demo_admin").check_password(CLAVE))

    def test_exige_la_variable_y_una_clave_valida(self):
        with self.assertRaises(CommandError):
            sembrar(clave=None)
        with self.assertRaises(CommandError):
            sembrar(clave="123")
        self.assertEqual(get_user_model().objects.count(), 0)

    @override_settings(DEBUG=False)
    def test_fuera_de_debug_pide_confirmacion(self):
        with self.assertRaises(CommandError):
            sembrar(confirmar=False)
        self.assertEqual(get_user_model().objects.count(), 0)
        sembrar()
        self.assertEqual(get_user_model().objects.count(), len(USUARIOS))

    @override_settings(DEBUG=False)
    def test_desactivar_no_borra_y_se_puede_sin_confirmar(self):
        sembrar()
        call_command("sembrar_demo", "--desactivar", stdout=io.StringIO())
        U = get_user_model()
        self.assertEqual(U.objects.count(), len(USUARIOS))
        self.assertFalse(U.objects.filter(is_active=True).exists())

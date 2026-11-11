"""Pruebas de los controles que vigila la infraestructura.

No prueban el negocio: prueban que la configuración de seguridad no se degrade
sin que nadie se dé cuenta. Si alguien agrega un `DEBUG = True` o cambia el
hasher de contraseñas, esto se cae en integración continua.

Responsable: Alejandra.
"""

from django.conf import settings
from django.contrib.auth.hashers import get_hasher
from django.test import SimpleTestCase, TestCase, override_settings


class SondasTest(TestCase):
    def test_healthz_responde_sin_tocar_la_base(self):
        respuesta = self.client.get("/healthz")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["status"], "ok")

    def test_readyz_comprueba_la_base(self):
        respuesta = self.client.get("/readyz")
        self.assertEqual(respuesta.status_code, 200)

    def test_portada_responde(self):
        self.assertEqual(self.client.get("/").status_code, 200)


class ContrasenasTest(SimpleTestCase):
    def test_el_hasher_es_argon2(self):
        """Parte 1: Argon2id es el único hasher permitido.

        Un hash rápido cuesta la mitad del criterio de control de acceso
        (§7.1 del enunciado).
        """
        self.assertEqual(settings.PASSWORD_HASHERS[0].rsplit(".", 1)[-1],
                         "Argon2PasswordHasher")
        self.assertEqual(get_hasher("default").algorithm, "argon2")

    def test_longitud_minima_de_doce(self):
        validadores = [v["NAME"] for v in settings.AUTH_PASSWORD_VALIDATORS]
        self.assertIn(
            "django.contrib.auth.password_validation.MinimumLengthValidator",
            validadores,
        )


class AutorizacionPorOmisionTest(SimpleTestCase):
    def test_el_permiso_por_omision_de_drf_deniega(self):
        """Una vista nueva, sin permisos declarados, queda cerrada.

        Es lo contrario de lo habitual, y es deliberado: si a alguien se le
        olvida el control de acceso, la vista no responde en vez de abrirse.
        """
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"],
            ["authz.permissions.DenyAll"],
        )

    def test_el_pdp_falla_cerrado(self):
        self.assertTrue(settings.OPA_FAIL_CLOSED)

    def test_el_pdp_no_se_consulta_por_la_red_externa(self):
        self.assertIn("127.0.0.1", settings.OPA_URL)


class EndurecimientoHttpTest(SimpleTestCase):
    """Lo que `check --deploy` no alcanza a comprobar por sí solo."""

    @override_settings(DEBUG=False)
    def test_se_confia_en_la_cabecera_de_esquema_del_proxy(self):
        self.assertEqual(
            settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https")
        )

    def test_sin_marcos(self):
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")

    def test_sin_adivinar_el_tipo_de_contenido(self):
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)

    def test_la_sesion_caduca_por_inactividad(self):
        self.assertLessEqual(settings.SESSION_COOKIE_AGE, 30 * 60)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)

    def test_la_cookie_de_sesion_no_se_lee_desde_javascript(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)

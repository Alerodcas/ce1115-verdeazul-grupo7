"""Entrega, fuera de banda, el secreto del segundo factor de una persona.

    python manage.py secreto_mfa demo_verificador

Imprime el URI otpauth:// y la clave en base32 para cargarla a mano en una
aplicación autenticadora. La web nunca muestra el secreto: así quien solo tenga la
contraseña no puede enrolarse. Fuera de DEBUG exige --confirmar.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from interfaz import totp


class Command(BaseCommand):
    help = "Muestra el secreto TOTP de una persona para enrolarla en su aplicación autenticadora."

    def add_arguments(self, parser):
        parser.add_argument("usuario")
        parser.add_argument("--confirmar", action="store_true",
                            help="Obligatorio fuera de DEBUG: el secreto sale por pantalla.")

    def handle(self, *args, usuario, confirmar, **opts):
        if not settings.DEBUG and not confirmar:
            raise CommandError("DEBUG está apagado: el secreto saldría en un entorno real. "
                               "Repita con --confirmar.")
        u = get_user_model().objects.filter(username=usuario).first()
        if u is None:
            raise CommandError(f"No existe la cuenta {usuario!r}.")
        self.stdout.write(f"Clave (base32): {totp.secreto_base32(u)}")
        self.stdout.write(f"URI:            {totp.uri_enrolamiento(u)}")

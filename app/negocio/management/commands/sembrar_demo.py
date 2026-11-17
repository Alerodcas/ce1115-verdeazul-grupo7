"""Siembra los datos mínimos para demostrar el sistema y sacar la evidencia.

Crea los seis grupos de rol, una persona por cada rol (más tres de apoyo para las
pruebas de separación de funciones), una finca con su técnico y dueño, y dos
períodos. **No crea mediciones, enmiendas ni cuentas**: esas se hacen por la API,
para que cada una deje su entrada en la bitácora. Si se sembraran por la base, la
evidencia mostraría acciones sin rastro.

Contraseña: sale de la variable de entorno VERDEAZUL_DEMO_PASSWORD. No se escribe
en el código ni se imprime. Se aplica solo a las cuentas que se crean.

    VERDEAZUL_DEMO_PASSWORD=... python manage.py sembrar_demo --confirmar
    python manage.py sembrar_demo --desactivar          # al terminar la demostración

Es idempotente. Todas las cuentas llevan el prefijo `demo_`.
"""

import os
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from negocio.models import ROLES, Finca, Periodo

# usuario → rol (grupo). Los tres últimos son de apoyo.
USUARIOS = {
    "demo_tecnico": "Tecnico de campo",
    "demo_verificador": "Verificador",
    "demo_admin": "Administrador",
    "demo_auditor": "Auditor externo",
    "demo_dueno": "Dueno de finca",
    "demo_gerencia": "Gerencia de Certificacion",
    "demo_tecnico_ajeno": "Tecnico de campo",  # sin finca asignada: prueba S1
    "demo_admin2": "Administrador",  # ejecuta lo que aprueba otra persona (C6)
    "demo_beneficiario": "Verificador",  # cuenta sobre la que se pide un cambio (C6)
}


class Command(BaseCommand):
    help = "Siembra roles, usuarios demo, una finca y dos períodos. Idempotente."

    def add_arguments(self, parser):
        parser.add_argument("--confirmar", action="store_true",
                            help="Obligatorio fuera de DEBUG (p. ej. contra Neon).")
        parser.add_argument("--desactivar", action="store_true",
                            help="Desactiva las cuentas demo_* (no las borra) y termina.")

    def handle(self, *args, confirmar, desactivar, **opts):
        if not settings.DEBUG and not confirmar and not desactivar:
            raise CommandError("DEBUG está apagado: esto parece un entorno real. Repita con --confirmar.")
        Usuario = get_user_model()

        if desactivar:
            n = Usuario.objects.filter(username__in=USUARIOS, is_active=True).update(is_active=False)
            self.stdout.write(f"Cuentas demo desactivadas: {n}.")
            return

        clave = os.environ.get("VERDEAZUL_DEMO_PASSWORD", "")
        if not clave:
            raise CommandError("Falta VERDEAZUL_DEMO_PASSWORD (no se escribe en el código ni se imprime).")
        try:
            validate_password(clave)
        except ValidationError as e:
            raise CommandError("La contraseña no cumple la política: " + " ".join(e.messages)) from e

        with transaction.atomic():
            grupos = {r: Group.objects.get_or_create(name=r)[0] for r in ROLES}
            creados = []
            usuarios = {}
            for nombre, rol in USUARIOS.items():
                u, nuevo = Usuario.objects.get_or_create(username=nombre)
                if nuevo:
                    u.set_password(clave)
                    u.save()
                    creados.append(nombre)
                u.is_active = True
                u.save(update_fields=["is_active"])
                u.groups.add(grupos[rol])
                usuarios[nombre] = u

            finca, _ = Finca.objects.get_or_create(
                nombre="Finca Demo La Esperanza",
                defaults={"ubicacion": "Zona de prueba", "area_ha": "12.50",
                          "propietario": usuarios["demo_dueno"]},
            )
            finca.tecnicos.add(usuarios["demo_tecnico"])
            Periodo.objects.get_or_create(
                etiqueta="DEMO-ABIERTO",
                defaults={"inicio": date(2026, 1, 1), "fin": date(2026, 12, 31), "abierto": True})
            Periodo.objects.get_or_create(
                etiqueta="DEMO-CERRADO",
                defaults={"inicio": date(2025, 1, 1), "fin": date(2025, 12, 31), "abierto": False})

        self.stdout.write(
            f"Roles: {len(grupos)}. Cuentas demo: {len(USUARIOS)} ({len(creados)} nuevas). "
            f"Finca id={finca.pk}. Contraseña: la de VERDEAZUL_DEMO_PASSWORD."
        )

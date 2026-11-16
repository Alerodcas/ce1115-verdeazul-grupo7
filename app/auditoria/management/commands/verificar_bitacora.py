from django.core.management.base import BaseCommand, CommandError

from auditoria.servicio import verificar_cadena


class Command(BaseCommand):
    help = "Recalcula la cadena de hashes de la bitácora. Sale con error si está rota."

    def handle(self, *args, **opts):
        r = verificar_cadena()
        if not r.ok:
            raise CommandError(f"Cadena rota en la entrada {r.primera_rota}: {r.motivo}")
        self.stdout.write(f"Bitácora íntegra: {r.revisadas} entradas.")

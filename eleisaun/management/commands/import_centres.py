from django.core.management.base import BaseCommand, CommandError

from eleisaun.importers import decode, import_centres


class Command(BaseCommand):
    help = "Impor sentru votasaun husi CSV. Sein --apply = de'it validasaun (dry-run)."

    def add_arguments(self, p):
        p.add_argument("path")
        p.add_argument("--apply", action="store_true")

    def handle(self, *a, **o):
        try:
            with open(o["path"], "rb") as f:
                text = decode(f.read())
        except (OSError, ValueError) as e:
            raise CommandError(f"La bele le'e file: {e}")
        rep = import_centres(text, apply=o["apply"])
        for n, msg in rep["errors"][:50]:
            self.stderr.write(f"linha {n}: {msg}")
        self.stdout.write(f"linha: {rep['rows']} · foun: {rep['new']} · atualiza: {rep['updated']} · hanesan: {rep['unchanged']}")
        if rep["errors"]:
            raise CommandError(f"{len(rep['errors'])} error — la grava buat ida.")
        self.stdout.write(self.style.SUCCESS("GRAVA ONA." if rep["applied"] else "Dry-run OK (uza --apply atu grava)."))

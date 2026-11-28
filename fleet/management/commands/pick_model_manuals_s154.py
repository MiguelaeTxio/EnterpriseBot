# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/pick_model_manuals_s154.py
"""
S154 (invasora, 28/11) -- elige el manual de los modelos que tienen
varias copias: se queda la que tiene más páginas (la completa) y, si
empatan, la que menos pesa (mejor para el móvil), solo entre manuales
de uso (el despiece es otro documento). Solo se aplica si las demás son
copias (mismas páginas) o trozos (como mucho un 30 % de sus páginas);
si no, puede ser otro manual (p. ej. el del camión y el de la
plataforma) y se deja para decidir a mano. Las demás quedan
descartadas en la BD; no se borra nada del cubo ni de Microsoft 365
(fleet.manual_counters_service.set_model_manual).

Sin --apply solo lista qué copia se quedaría en cada modelo. Cuenta las
páginas abriendo cada PDF (PyMuPDF, sin OCR). Escribe en pantalla y en
su propio fichero de log a la vez (com-standards 0bis), con progreso y
hora estimada de fin (0ter).

---

S154 -- picks the manual of the models with several copies.
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand

from fleet.models import MachineModel

# Una copia con hasta este porcentaje de las páginas de la elegida es un
# trozo; con más (y distinto número), puede ser otro manual.
FRAGMENT = 0.3


class Command(BaseCommand):
    """
    Picks the manual of the models with several copies.

    ---

    Elige el manual de los modelos con varias copias.
    """

    help = ("Elige el manual de los modelos con varias copias (sin "
            "--apply solo lista).")

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, text, stamp=True):
        line = ("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
                if stamp else text)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options)
        finally:
            self._log_handle.close()

    @staticmethod
    def _pages(entry):
        import fitz

        from spare_parts.gcs_service import download_bytes

        try:
            data = download_bytes(entry.bucket, entry.blob_name)
            with fitz.open(stream=data, filetype="pdf") as document:
                return document.page_count
        except Exception:  # noqa: BLE001 -- PDF dañado o no PDF
            return 0

    def _run(self, options):
        from fleet import manual_counters_service as service

        # Modelos a los que se fijó un manual que no es de uso (el
        # despiece contaba como manual antes del 28/11): se les quita.
        wrong = MachineModel.objects.filter(manual__isnull=False).exclude(
            manual__document_type__code=service.USE_MANUAL_CODE)
        for model in wrong:
            self._log("%s: su manual %s no es de uso; %s." % (
                model.name, model.manual.name,
                "se quita" if options["apply"] else "se quitaría"))
            if options["apply"]:
                model.manual = None
                model.save(update_fields=["manual"])
        todo = []
        for model in MachineModel.objects.filter(
                manual__isnull=True).prefetch_related("machines"):
            manuals = service.machine_manuals(list(model.machines.all()))
            if len(manuals) > 1:
                todo.append((model, manuals))
        total = len(todo)
        self._log("Modelos con varias copias y sin manual elegido: %s."
                  % total)
        start = datetime.now()
        kept = discarded = 0
        review = []
        for position, (model, manuals) in enumerate(todo, 1):
            eta = ""
            if position > 1:
                elapsed = (datetime.now() - start).total_seconds()
                rest = elapsed / (position - 1) * (total - position + 1)
                eta = " -- ETA %dm%02ds (fin aprox. %s)" % (
                    rest // 60, rest % 60,
                    (datetime.now() + timedelta(seconds=rest))
                    .strftime("%H:%M:%S"))
            self._log("[%s/%s] %s%s" % (position, total, model.name, eta))
            rows = [(self._pages(e), e) for e in manuals]
            rows.sort(key=lambda r: (-r[0], r[1].size_bytes or 0))
            pages, chosen = rows[0]
            if pages == 0:
                self._log("   Ningún PDF se puede abrir; se deja sin "
                          "elegir.")
                continue
            doubtful = [e for count, e in rows[1:]
                         if count != pages and count > pages * FRAGMENT]
            for count, entry in rows:
                self._log("   %s id %s: %s -- %s páginas, %.1f MB" % (
                    "SE QUEDA " if entry.pk == chosen.pk else (
                        "¿OTRO?  " if entry in doubtful else "descarta"),
                    entry.pk, entry.name, count,
                    (entry.size_bytes or 0) / 1048576), stamp=False)
            if doubtful:
                review.append(model.name)
                self._log("   Puede ser otro manual: se deja para decidir "
                          "a mano.", stamp=False)
                continue
            kept += 1
            discarded += len(rows) - 1
            if options["apply"]:
                service.set_model_manual(model, chosen)
        self._log("", stamp=False)
        self._log("RESUMEN", stamp=False)
        self._log("Modelos con manual %s: %s" % (
            "elegido" if options["apply"] else "a elegir", kept),
            stamp=False)
        self._log("Copias %s en la BD (siguen en el cubo): %s" % (
            "descartadas" if options["apply"] else "a descartar",
            discarded), stamp=False)
        self._log("Para decidir a mano (puede haber otro manual): %s" %
                  len(review), stamp=False)
        for name in review:
            self._log("   %s" % name, stamp=False)
        if not options["apply"]:
            self._log("Sin --apply: no se ha cambiado nada.", stamp=False)

# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/extract_counters_all_s154.py
"""
S154 (invasora, 28/11) -- busca los contadores en el manual de todos
los modelos que ya tienen manual y aún no tienen ninguna imagen de
contadores (fleet.manual_counters_service.extract_for_model).

Sin --apply no llama a Gemini: abre cada manual, cuenta las páginas
que se le mandarían y estima el coste (Gemini 3.5 Flash, 1,50 $ el
millón de tokens de entrada y 9 $ el de salida). Con --apply busca;
--ids limita a esos modelos. Escribe en pantalla y en su propio
fichero de log a la vez, con progreso y hora estimada de fin
(com-standards 0bis/0ter).

---

S154 -- finds the counters in the manual of every model still without
counter images; without --apply it only estimates the cost.
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand

from fleet.models import MachineModel

# Tokens por página de PDF (imagen de la página + su texto) y por
# petición de respuesta (JSON + razonamiento bajo): por lo alto.
TOKENS_PER_PAGE = 800
OUTPUT_TOKENS_PER_REQUEST = 3000
USD_PER_INPUT_TOKEN = 1.5 / 1e6
USD_PER_OUTPUT_TOKEN = 9.0 / 1e6


class Command(BaseCommand):
    """
    Finds the counters for every model still without images.

    ---

    Busca los contadores de todos los modelos que aún no tienen.
    """

    help = ("Busca los contadores en el manual de los modelos sin "
            "imágenes (sin --apply solo estima el coste).")

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--ids", default="",
                            help="Ids de modelo separados por comas.")
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

    def _models(self, options):
        models = MachineModel.objects.filter(
            manual__isnull=False, counter_images__isnull=True
        ).select_related("manual").order_by("name")
        ids = {int(x) for x in options["ids"].split(",") if x.strip()}
        if ids:
            models = models.filter(pk__in=ids)
        return list(models)

    def _eta(self, start, done, total):
        elapsed = (datetime.now() - start).total_seconds()
        eta = elapsed / done * (total - done) if done else 0
        return " -- ETA %dm%02ds (fin aprox. %s)" % (
            eta // 60, eta % 60,
            (datetime.now() + timedelta(seconds=eta)).strftime("%H:%M:%S"))

    def _run(self, options):
        models = self._models(options)
        self._log("Modelos con manual y sin imágenes de contadores: %s."
                  % len(models))
        if options["apply"]:
            self._extract(models)
        else:
            self._estimate(models)

    def _estimate(self, models):
        import fitz

        from fleet import manual_counters_service as service
        from spare_parts.gcs_service import download_bytes

        start = datetime.now()
        rows = []
        for position, model in enumerate(models, 1):
            entry = model.manual
            line = "[%s/%s] id %s %s" % (position, len(models), model.pk,
                                         model.name)
            try:
                document = fitz.open(
                    stream=download_bytes(entry.bucket, entry.blob_name),
                    filetype="pdf")
            except Exception as exc:  # noqa: BLE001 -- PDF dañado
                self._log(line + ": no se abre (%s)." % str(exc)[:80]
                          + self._eta(start, position, len(models)))
                continue
            pages = service._candidate_pages(document)
            scanned = pages is None
            if scanned:
                pages = list(range(min(document.page_count,
                                       service.SCANNED_MAX_PAGES)))
            requests = sum(1 for _ in service._batches(document, pages)) \
                if pages else 0
            cost = (len(pages) * TOKENS_PER_PAGE * USD_PER_INPUT_TOKEN
                    + requests * OUTPUT_TOKENS_PER_REQUEST
                    * USD_PER_OUTPUT_TOKEN)
            rows.append((model, document.page_count, len(pages), requests,
                         scanned, cost))
            self._log("%s: %s págs., se mandan %s%s, %s peticiones, "
                      "~%.2f $" % (line, document.page_count, len(pages),
                                   " (escaneado)" if scanned else "",
                                   requests, cost)
                      + self._eta(start, position, len(models)))
        self._log("", stamp=False)
        self._log("RESUMEN (sin --apply: no se ha llamado a Gemini)",
                  stamp=False)
        text = [r for r in rows if not r[4]]
        scanned = [r for r in rows if r[4]]
        for label, group in (("Con texto", text), ("Escaneados", scanned)):
            self._log("%s: %s modelos, %s páginas, ~%.2f $" % (
                label, len(group), sum(r[2] for r in group),
                sum(r[5] for r in group)), stamp=False)
        self._log("Total: ~%.2f $" % sum(r[5] for r in rows), stamp=False)
        self._log("Ids con texto: %s" % ",".join(
            str(r[0].pk) for r in text), stamp=False)
        self._log("Ids escaneados: %s" % ",".join(
            str(r[0].pk) for r in scanned), stamp=False)

    def _extract(self, models):
        from fleet import manual_counters_service as service

        start = datetime.now()
        total_saved = 0
        for position, model in enumerate(models, 1):
            self._log("[%s/%s] id %s %s" % (position, len(models), model.pk,
                                            model.name)
                      + (self._eta(start, position - 1, len(models))
                         if position > 1 else ""))
            try:
                saved = service.extract_for_model(model, self._log)
            except Exception as exc:  # noqa: BLE001 -- se sigue
                self._log("   Falló (%s), se sigue." % str(exc)[:120])
                continue
            total_saved += saved
            self._log("   Imágenes pendientes de revisar: %s." % saved)
        self._log("", stamp=False)
        self._log("RESUMEN", stamp=False)
        self._log("Modelos: %s. Imágenes nuevas pendientes de revisar: %s."
                  % (len(models), total_saved), stamp=False)

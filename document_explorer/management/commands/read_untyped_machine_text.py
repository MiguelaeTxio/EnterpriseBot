# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/read_untyped_machine_text.py
"""
H30 (S118), punto 7 de la hoja de ruta -- PASO A: lectura única del
texto de los documentos SIN TIPO de máquinas ACTIVAS, cacheado en
`DocumentIndexEntry.ocr_text`.

Motor (decisión de Miguel Ángel en S118: "lo que veas más conveniente
siempre que tenga un gasto moderado"): el mismo de H31/H35/H36 --
texto incrustado del PDF primero (gratis) y, solo si no hay, Cloud
Vision (`cloud_vision_service`), acotado a las 2 primeras páginas, así
que como mucho 2 unidades facturables por documento. Nunca Tesseract
en el servidor (S62/S102).

Este paso SOLO lee y guarda el texto: nunca toca `document_type`,
máquina, fechas ni GCS. La clasificación (paso B) se hace después sobre
el texto ya guardado, gratis y repetible. Un documento con `ocr_text`
ya relleno no se vuelve a leer -- relanzar el comando nunca paga dos
veces el mismo documento (los que no dieron texto legible sí se
reintentan, y el resumen los lista).

`--limit N` para una prueba corta; `--shard K/N` (1-based) para
repartir en varias consolas sin solape (`entry_id % N == K-1`).
Log propio con heartbeat y ETA (com-standards 0bis/0ter).
---
H30 (S118), roadmap item 7 -- STEP A: one-off text read of UNTYPED
documents of ACTIVE machines, cached in `ocr_text`. Embedded PDF text
first, Cloud Vision (first 2 pages) only when there is none. Never
changes type, machine, dates or GCS.
"""
import time
from datetime import datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from document_explorer.cloud_vision_service import (
    cloud_vision_text,
    pdf_embedded_text,
)
from document_explorer.models import DocumentIndexEntry
from fleet.models import MachineAsset
from spare_parts.gcs_service import download_bytes

BUCKET = "cgs_grupo_alvarez"
SUPPORTED_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png")


class Command(BaseCommand):
    help = (
        "H30 (S118) -- paso A del punto 7: lee y guarda en ocr_text el "
        "texto de los documentos sin tipo de maquinas activas (texto "
        "incrustado y, si no hay, Cloud Vision)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)
        # H30 (S118), punto 8: misma lectura para los documentos YA
        # tipados de tipos que caducan que siguen sin ninguna fecha.
        parser.add_argument(
            "--caducables-sin-fecha", action="store_true",
            dest="expiring_undated",
            help="Tipados con caducidad y sin ninguna fecha, en vez de "
                 "los sin tipo.",
        )
        parser.add_argument(
            "--shard", default="1/1",
            help="K/N, 1-based: procesa los documentos con id %% N == K-1.",
        )
        parser.add_argument(
            "--log-file", required=True,
            help="Log propio (pantalla y archivo a la vez, 0bis).",
        )

    def _log(self, message):
        self._log_plain(
            "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message),
        )

    def _log_plain(self, message):
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        try:
            shard_k, shard_n = (int(x) for x in options["shard"].split("/"))
        except ValueError:
            raise CommandError("--shard debe ser K/N, p. ej. 1/3.")
        if not 1 <= shard_k <= shard_n:
            raise CommandError("--shard: K debe estar entre 1 y N.")
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(
                shard_k, shard_n, options["limit"],
                options["expiring_undated"],
            )
        finally:
            self._log_handle.close()

    def _run(self, shard_k, shard_n, limit, expiring_undated=False):
        machine_ct = ContentType.objects.get_for_model(MachineAsset)
        active_pks = list(MachineAsset.objects.filter(
            is_active=True,
        ).values_list("pk", flat=True))
        scope = (
            {
                "document_type__tracks_expiry": True,
                "expiry_date__isnull": True, "issue_date__isnull": True,
            } if expiring_undated else {"document_type__isnull": True}
        )
        entries = [
            entry for entry in DocumentIndexEntry.objects.filter(
                bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
                **scope,
                domain_content_type=machine_ct,
                domain_object_id__in=active_pks,
                ocr_text="",
                deleted_at__isnull=True, purged_at__isnull=True,
            ).only("id", "bucket", "blob_name", "name").order_by("id")
            if entry.id % shard_n == shard_k - 1
            and entry.name.lower().endswith(SUPPORTED_EXTENSIONS)
        ]
        if limit:
            entries = entries[:limit]
        total = len(entries)
        self._log(
            "PASO A (lectura de texto, solo escribe ocr_text) -- shard "
            "%d/%d -- %d documentos %s de maquinas activas sin "
            "texto guardado%s" % (
                shard_k, shard_n, total,
                "TIPADOS QUE CADUCAN SIN FECHA" if expiring_undated
                else "sin tipo",
                " (limitado a %d)" % limit if limit else "",
            )
        )

        by_embedded = by_vision = empty = failed = vision_pages = 0
        empty_list, failed_list = [], []
        start_time = datetime.now()
        last_beat = time.monotonic()

        for index, entry in enumerate(entries, start=1):
            close_old_connections()
            try:
                data = download_bytes(entry.bucket, entry.blob_name)
                text = ""
                engine = ""
                if entry.name.lower().endswith(".pdf"):
                    text = pdf_embedded_text(data)
                    engine = "incrustado"
                if not text.strip():
                    text = cloud_vision_text(data, entry.name)
                    engine = "Cloud Vision"
                    vision_pages += (
                        2 if entry.name.lower().endswith(".pdf") else 1
                    )
            except Exception as exc:  # noqa: BLE001 -- se registra y sigue
                failed += 1
                failed_list.append("id=%d  %s  (%s)" % (
                    entry.id, entry.blob_name, exc,
                ))
                self._log("ERROR id=%d %s: %s" % (entry.id, entry.name, exc))
                continue

            if text.strip():
                DocumentIndexEntry.objects.filter(pk=entry.pk).update(
                    ocr_text=text,
                )
                if engine == "incrustado":
                    by_embedded += 1
                else:
                    by_vision += 1
                self._log("LEIDO (%s, %d caracteres) id=%d %s" % (
                    engine, len(text), entry.id, entry.name,
                ))
            else:
                empty += 1
                empty_list.append("id=%d  %s" % (entry.id, entry.blob_name))
                self._log("SIN TEXTO LEGIBLE id=%d %s" % (
                    entry.id, entry.name,
                ))

            if index % 25 == 0 or time.monotonic() - last_beat >= 30 \
                    or index == total:
                last_beat = time.monotonic()
                elapsed = (datetime.now() - start_time).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                hora_fin = (
                    datetime.now() + timedelta(seconds=eta_seg)
                ).strftime("%H:%M:%S")
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                    "-- incrustado=%d, cloud_vision=%d, sin_texto=%d, "
                    "errores=%d" % (
                        index, total, index * 100 // total if total else 100,
                        int(eta_seg // 60), int(eta_seg % 60), hora_fin,
                        by_embedded, by_vision, empty, failed,
                    )
                )

        self._log_plain("=== RESUMEN PASO A (shard %d/%d) ===" % (
            shard_k, shard_n,
        ))
        self._log_plain("    documentos procesados: %d" % total)
        self._log_plain("    texto incrustado (gratis): %d" % by_embedded)
        self._log_plain("    leidos con Cloud Vision: %d" % by_vision)
        self._log_plain(
            "    unidades de Cloud Vision (maximo, 2 por PDF): %d"
            % vision_pages
        )
        self._log_plain("    sin texto legible: %d" % empty)
        self._log_plain("    errores: %d" % failed)
        if empty_list:
            self._log_plain("--- SIN TEXTO LEGIBLE ---")
            for line in empty_list:
                self._log_plain("    %s" % line)
        if failed_list:
            self._log_plain("--- ERRORES ---")
            for line in failed_list:
                self._log_plain("    %s" % line)

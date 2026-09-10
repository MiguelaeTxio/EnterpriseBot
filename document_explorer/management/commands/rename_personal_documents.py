# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/rename_personal_documents.py
"""
H31 (S98) -- renombrado canonico masivo de TODO el dominio PERSONAL
(activos e inactivos), sin llamar a Gemini en ningun momento: usa
`apply_personal_canonical_rename()` (`classification_service.py`),
que construye el nombre fijo a partir de datos YA resueltos en BD
(`document_type`, `PersonIdentity`, `expiry_date`/`issue_date`) --
ningun OCR, ninguna llamada a la API de Gemini. Este comando es
deliberadamente delgado: toda la logica real vive en la funcion de
`classification_service.py` para que sea reutilizable desde cualquier
otro sitio (el futuro pipeline de clasificacion predictiva sin
Gemini que Miguel Angel planea entrenar, u otro comando futuro).

Decision explicita de Miguel Angel (S98): alcance final, TODO
PERSONAL -- 8.358 documentos vivos confirmados en esta sesion, 0 sin
`document_type` asignado -- no solo trabajadores activos. Para los
documentos sin `expiry_date` ni `issue_date` (historicos, versiones
antiguas de un mismo tipo, trabajadores de baja...) se usa una fecha
ficticia fija -- 2021-01-01, festivo nacional a proposito, ningun
documento real de la empresa se emite o vence ese dia -- solo dentro
del nombre de archivo generado, nunca escrita en las columnas reales
de fecha. El ordinal ya existente del propio `naming_service`
(mismos apellidos + nombre + tipo + fecha) diferencia automaticamente
varios documentos sin fecha real de la misma persona y tipo (p. ej.
varios DNI antiguos de un mismo trabajador).

Verificado en linea (S98): el coste de CPU real de este barrido en la
consola de PythonAnywhere es insignificante frente a la cuota diaria
-- son lecturas/escrituras SQL indexadas y formateo de texto, nada
parecido al OCR que si esta vetado en esa consola (`com-standards`,
seccion "COSTE DE CPU DE OCR"). Por eso este comando corre entero
aqui, sin necesidad de ninguna VM de Google Compute Engine.

DRY-RUN POR DEFECTO. Con --apply escribe de verdad.

Verboso por diseno (`com-standards` 0bis/0ter): heartbeat con ETA
cada 25 elementos procesados -- volumen (miles) conocido de antemano,
no se espera a que el barrido demuestre ser largo para anadirlo.
"""
import datetime

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.classification_service import (
    apply_personal_canonical_rename,
)
from document_explorer.models import DocumentIndexEntry, PersonIdentity

# H31 (S98). Fecha ficticia fija para documentos PERSONAL sin
# expiry_date ni issue_date -- decision explicita de Miguel Angel: el
# 1 de enero es festivo nacional, ningun documento real de la empresa
# se emite o vence ese dia. Solo aparece dentro del nombre de
# archivo, nunca en las columnas reales de fecha.
FICTITIOUS_DATE = datetime.date(2021, 1, 1)

# com-standards, seccion 0bis: recomendado N=25 o el 5% del total, lo
# que sea menor. Con miles de documentos, 25 es el valor menor real.
HEARTBEAT_EVERY = 25


class Command(BaseCommand):
    help = (
        "H31 (S98) -- renombrado canonico masivo de todo el dominio "
        "PERSONAL sin Gemini, via apply_personal_canonical_rename(). "
        "Dry-run por defecto, --apply para escribir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help=(
                "Procesa como maximo N documentos, en orden de id "
                "(para pruebas rapidas antes del barrido completo)."
            ),
        )
        parser.add_argument(
            "--no-fictitious-date", action="store_true",
            help=(
                "No usar la fecha ficticia 2021-01-01 -- deja tal "
                "cual cualquier documento sin expiry_date ni "
                "issue_date (motivo 'sin_fecha' en el resumen)."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        limit = options["limit"]
        fictitious_date = (
            None if options["no_fictitious_date"] else FICTITIOUS_DATE
        )

        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        queryset = (
            DocumentIndexEntry.objects.filter(
                domain_content_type=person_ct,
                entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True,
                purged_at__isnull=True,
            )
            .select_related("document_type")
            .prefetch_related("domain_object")
            .order_by("id")
        )
        total = queryset.count()
        if limit:
            queryset = queryset[:limit]
            total = min(total, limit)

        self.stdout.write(
            "=== INICIO (%s) -- %d documentos PERSONAL en alcance, "
            "fecha ficticia %s ==="
            % (
                "APLICADO" if apply_changes else "DRY-RUN, nada escrito",
                total,
                fictitious_date.isoformat() if fictitious_date else "DESACTIVADA",
            )
        )

        stats = {
            "renombrados": 0, "ya_correctos": 0, "con_fecha_ficticia": 0,
            "sin_persona_resuelta": 0, "sin_tipo": 0, "sin_fecha": 0,
        }
        start_time = datetime.datetime.now()
        procesados = 0
        # H31 (S98): compartido a lo largo de TODO el lote (dry-run
        # incluido) para que dos documentos que colisionan entre si
        # dentro de esta misma pasada -- p. ej. varios DNI antiguos
        # sin fecha de la misma persona, agrupados por la fecha
        # ficticia -- reciban ya el ordinal correcto en la vista
        # previa, sin depender de que _virtual_location_taken vea
        # algo que todavia no se ha escrito en BD.
        reserved_names = set()

        for entry in queryset:
            used_real_date = bool(entry.expiry_date or entry.issue_date)
            # H31 (S98), incidente real: apply_personal_canonical_rename
            # muta entry.name EN EL MISMO OBJETO cuando apply_changes=
            # True -- capturar el nombre original ANTES de la llamada,
            # nunca leerlo después, o el log muestra "X -> X" en vez
            # del cambio real (detectado en el --apply de 8.358 sobre
            # producción: los 8.283 renombrados quedaron bien escritos
            # en BD, pero el log entero mostraba el nombre ya mutado
            # a ambos lados de la flecha).
            original_name = entry.name
            result = apply_personal_canonical_rename(
                entry, fictitious_date=fictitious_date,
                apply_changes=apply_changes,
                reserved_names=reserved_names,
            )
            procesados += 1

            if result["reason"]:
                stats[result["reason"]] += 1
            elif result["renamed"]:
                stats["renombrados"] += 1
                if not used_real_date:
                    stats["con_fecha_ficticia"] += 1
                self.stdout.write(
                    "%s  id=%d  %s -> %s"
                    % (
                        "RENOMBRADO" if apply_changes else "CANDIDATO",
                        entry.pk, original_name, result["new_name"],
                    )
                )
            else:
                stats["ya_correctos"] += 1

            if procesados % HEARTBEAT_EVERY == 0 or procesados == total:
                elapsed = (
                    datetime.datetime.now() - start_time
                ).total_seconds()
                eta_seg = (
                    (elapsed / procesados) * (total - procesados)
                    if procesados else 0
                )
                hora_fin = (
                    datetime.datetime.now()
                    + datetime.timedelta(seconds=eta_seg)
                ).strftime("%H:%M:%S")
                pct = int(procesados * 100 / total) if total else 100
                self.stdout.write(
                    "[%s] Progreso: %d/%d (%d%%) -- ETA %dm%02ds "
                    "(fin aprox. %s) -- renombrados=%d ya_correctos=%d"
                    % (
                        datetime.datetime.now().strftime("%H:%M:%S"),
                        procesados, total, pct,
                        int(eta_seg // 60), int(eta_seg % 60), hora_fin,
                        stats["renombrados"], stats["ya_correctos"],
                    )
                )

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))

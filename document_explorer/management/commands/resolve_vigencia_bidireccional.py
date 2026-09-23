# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/resolve_vigencia_bidireccional.py
"""
H30 (S82) -- corrige el desfase real detectado por Miguel Angel en el
panel: un DNI marcado obsoleto en la ficha de personal, mientras el
historial mostraba uno mas reciente marcado como vigente.

Causa raiz confirmada contra el codigo real de la propia sesion:
- `resolve_obsoleto_folder_flag.py` (S50) marca is_obsolete=True SOLO
  por el nombre de la carpeta ("obsolet*" en parent_path), sin mirar
  ninguna fecha -- disenado para DOC. MAQUINAS, pero su consulta no
  filtra por dominio, asi que tambien toca PERSONAL.
- `resolve_vigencia.py` (S50), el que si compara por fecha real,
  parte de `is_obsolete=False` -- un documento ya marcado True por la
  carpeta queda fuera de su comparacion para siempre, nunca se
  re-evalua ni se "asciende" de vuelta a vigente aunque tenga la
  fecha mas reciente de su grupo.

Este comando repite exactamente las mismas reglas ya aprobadas por
Miguel Angel en S50 (fecha efectiva = expiry_date si existe, si no
issue_date; anverso/reverso nunca compiten entre si; empates exactos
nunca se tocan; grupos sin al menos dos fechas reales quedan fuera),
pero sobre TODOS los miembros del grupo sin importar su is_obsolete
actual -- y corrige en los dos sentidos: marca obsoleto el perdedor
real, y desmarca (is_obsolete=False) el vigente real si estaba mal
marcado True solo por la carpeta.

No sustituye a resolve_vigencia.py ni a resolve_obsoleto_folder_flag.py
-- comando nuevo, independiente, para no arriesgar el comportamiento
ya probado de los dos existentes.

DRY-RUN POR DEFECTO. Con --apply escribe is_obsolete de verdad en las
filas que cambian de estado (en cualquiera de los dos sentidos) --
nunca toca blob_name/parent_path/name (4.12).

S117 -- tres correcciones antes de relanzarlo (incidente real de Miguel
Ángel: Carvajal González, pk=218, con un parte de baja del 19/10/2020
vigente y el del 22/10/2020, posterior, marcado obsoleto):
- --domain obligatorio (PERSONAL o MACHINE): nunca se recalcula todo a
  ciegas. MÁQUINAS no está fechado todavía (H30, punto 6 de su hoja de
  ruta).
- Excluye los tipos acumulables (DocumentTypeCatalog.is_cumulative,
  S107): varias instancias vigentes a la vez por diseño (cursos,
  entregas, nombramientos...) -- antes los habría dejado obsoletos.
- com-standards 0bis/0ter: --log-file obligatorio (pantalla y archivo
  a la vez, flush), heartbeat cada 25 grupos o 30 s con ETA y hora de
  fin, TODOS los cambios en el log (antes solo 80), resumen sin tiempos.
"""
import time
from datetime import datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Count

from document_explorer.models import DocumentIndexEntry, PersonIdentity
from fleet.models import MachineAsset


class Command(BaseCommand):
    help = (
        "H30 (S82) -- corrige is_obsolete comparando fecha real de "
        "TODOS los miembros de cada grupo (sujeto + tipo documental), "
        "sin importar su is_obsolete actual -- a diferencia de "
        "resolve_vigencia.py, puede desmarcar un documento que estaba "
        "mal marcado obsoleto solo por vivir en una carpeta OBSOLETO. "
        "Dry-run por defecto, usar --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe is_obsolete de verdad. Sin esta flag, solo informa.",
        )
        parser.add_argument(
            "--domain", required=True, choices=["PERSONAL", "MACHINE"],
            help="Dominio a recalcular (nunca los dos a la vez).",
        )
        parser.add_argument(
            "--log-file", required=True,
            help="Log propio (pantalla y archivo a la vez, com-standards 0bis).",
        )

    def _log(self, message):
        self._log_plain("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message))

    def _log_plain(self, message):
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options["apply"], options["domain"])
        finally:
            self._log_handle.close()

    def _run(self, apply_changes, domain):
        model = PersonIdentity if domain == "PERSONAL" else MachineAsset
        content_type = ContentType.objects.get_for_model(model)
        base = DocumentIndexEntry.objects.filter(
            entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__isnull=False,
            document_type__is_cumulative=False,
            domain_content_type=content_type,
            domain_object_id__isnull=False,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        )
        groups = list(
            base.values("domain_object_id", "document_type_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
        )
        total = len(groups)
        self._log(
            "MODO: %s -- dominio %s, tipos NO acumulables: %d grupos "
            "(sujeto + tipo) con mas de un documento" % (
                "APLICAR (escribe)" if apply_changes else "DRY-RUN (no escribe nada)",
                domain, total,
            )
        )

        stats = {
            "grupos_corregidos": 0,
            "filas_pasadas_a_obsoleto": 0,
            "filas_rescatadas_a_vigente": 0,
            "empates_exactos_sin_tocar": 0,
            "bloqueados_anverso_reverso": 0,
            "bloqueados_sin_fecha": 0,
        }
        start_time = datetime.now()
        last_beat = time.monotonic()

        for index, g in enumerate(groups, start=1):
            self._process_group(
                base, g, apply_changes, stats,
            )
            if (
                index % 25 == 0
                or time.monotonic() - last_beat >= 30
                or index == total
            ):
                last_beat = time.monotonic()
                elapsed = (datetime.now() - start_time).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                hora_fin = (
                    datetime.now() + timedelta(seconds=eta_seg)
                ).strftime("%H:%M:%S")
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s) "
                    "-- corregidos=%d, a_obsoleto=%d, rescatados=%d" % (
                        index, total, index * 100 // total,
                        int(eta_seg // 60), int(eta_seg % 60), hora_fin,
                        stats["grupos_corregidos"],
                        stats["filas_pasadas_a_obsoleto"],
                        stats["filas_rescatadas_a_vigente"],
                    )
                )

        self._log_plain("=== RESUMEN (%s, dominio %s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito", domain,
        ))
        self._log_plain("    grupos con mas de un documento: %d" % total)
        for key, value in stats.items():
            self._log_plain("    %s: %d" % (key, value))

    def _process_group(self, base, g, apply_changes, stats):
        entries = list(base.filter(
            domain_object_id=g["domain_object_id"],
            document_type_id=g["document_type_id"],
        ).select_related("document_type"))

        # Blindaje anverso/reverso (mismo criterio que
        # resolve_vigencia.py, S50) -- si CUALQUIER miembro del grupo es
        # la otra cara de un documento fisico, el grupo entero queda
        # fuera de la regla de fecha.
        if any(
            "REVERSO" in e.name.upper() or "ANVERSO" in e.name.upper()
            or "REVERSI" in e.name.upper()
            for e in entries
        ):
            stats["bloqueados_anverso_reverso"] += 1
            return

        dated = [
            (e, e.expiry_date or e.issue_date) for e in entries
            if e.expiry_date or e.issue_date
        ]
        if len(dated) < 2:
            stats["bloqueados_sin_fecha"] += 1
            return

        max_date = max(d for _, d in dated)
        winners = [e for e, d in dated if d == max_date]
        losers = [e for e, d in dated if d < max_date]

        if len(winners) > 1 and not losers:
            stats["empates_exactos_sin_tocar"] += 1
            return

        grupo_cambio = False
        winner_pks = {e.pk for e in winners}
        for entry in entries:
            if entry.pk in winner_pks:
                # Es el ganador real -- si estaba mal marcado obsoleto
                # (carpeta, backfill anterior a tener fechas...), se
                # rescata.
                if entry.is_obsolete:
                    stats["filas_rescatadas_a_vigente"] += 1
                    self._log(
                        "-> VIGENTE (rescatado)  sujeto=%s  tipo=%s  pk=%d  %s  "
                        "(fecha=%s)" % (
                            g["domain_object_id"], entry.document_type.code,
                            entry.pk, entry.name, max_date,
                        )
                    )
                    grupo_cambio = True
                    if apply_changes:
                        entry.is_obsolete = False
                        entry.save(update_fields=["is_obsolete"])
                continue
            # Cualquier otro miembro del grupo (con fecha real anterior,
            # o sin fecha) no puede seguir siendo Vigente a la vez que el
            # ganador real -- Miguel Angel, verbatim (S82): "no puede
            # haber varios documentos vigentes del mismo tipo, tenga o
            # no fecha el resto". Nunca se inventa SU fecha.
            if not entry.is_obsolete:
                stats["filas_pasadas_a_obsoleto"] += 1
                self._log(
                    "-> OBSOLETO  sujeto=%s  tipo=%s  pk=%d  %s  (fecha=%s, "
                    "vigente real=%s)" % (
                        g["domain_object_id"], entry.document_type.code,
                        entry.pk, entry.name,
                        entry.expiry_date or entry.issue_date, max_date,
                    )
                )
                grupo_cambio = True
                if apply_changes:
                    entry.is_obsolete = True
                    entry.save(update_fields=["is_obsolete"])
        if grupo_cambio:
            stats["grupos_corregidos"] += 1

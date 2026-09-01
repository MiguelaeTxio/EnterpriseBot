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
"""
from django.core.management.base import BaseCommand
from django.db.models import Count

from document_explorer.models import DocumentIndexEntry


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

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        base = DocumentIndexEntry.objects.filter(
            entry_kind=DocumentIndexEntry.KIND_FILE,
            document_type__isnull=False,
            domain_object_id__isnull=False,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        )
        groups = (
            base.values(
                "domain_content_type_id", "domain_object_id",
                "document_type_id",
            )
            .annotate(n=Count("id"))
            .filter(n__gt=1)
        )

        stats = {
            "grupos_corregidos": 0,
            "filas_pasadas_a_obsoleto": 0,
            "filas_rescatadas_a_vigente": 0,
            "empates_exactos_sin_tocar": 0,
            "bloqueados_anverso_reverso": 0,
            "bloqueados_sin_fecha": 0,
        }
        cambios = []

        for g in groups:
            entries = list(base.filter(
                domain_content_type_id=g["domain_content_type_id"],
                domain_object_id=g["domain_object_id"],
                document_type_id=g["document_type_id"],
            ))

            # Blindaje anverso/reverso (mismo criterio que
            # resolve_vigencia.py, S50) -- si CUALQUIER miembro del
            # grupo es la otra cara de un documento fisico, el grupo
            # entero queda fuera de la regla de fecha.
            if any(
                "REVERSO" in e.name.upper() or "ANVERSO" in e.name.upper()
                or "REVERSI" in e.name.upper()
                for e in entries
            ):
                stats["bloqueados_anverso_reverso"] += 1
                continue

            dated = [
                (e, e.expiry_date or e.issue_date) for e in entries
                if e.expiry_date or e.issue_date
            ]
            if len(dated) < 2:
                stats["bloqueados_sin_fecha"] += 1
                continue

            max_date = max(d for _, d in dated)
            winners = [e for e, d in dated if d == max_date]
            losers = [e for e, d in dated if d < max_date]

            if len(winners) > 1 and not losers:
                stats["empates_exactos_sin_tocar"] += 1
                continue

            grupo_cambio = False
            winner_pks = {e.pk for e in winners}
            for entry in entries:
                if entry.pk in winner_pks:
                    # Es el ganador real -- si estaba mal marcado
                    # obsoleto solo por la carpeta, se rescata.
                    if entry.is_obsolete:
                        stats["filas_rescatadas_a_vigente"] += 1
                        cambios.append((
                            "-> VIGENTE (rescatado)", entry.pk, entry.name,
                            entry.expiry_date or entry.issue_date, max_date,
                        ))
                        grupo_cambio = True
                        if apply_changes:
                            entry.is_obsolete = False
                            entry.save(update_fields=["is_obsolete"])
                    continue
                # Cualquier otro miembro del grupo (con fecha real
                # anterior, o sin fecha) no puede seguir siendo
                # Vigente a la vez que el ganador real -- Miguel
                # Angel, verbatim (S82): "no puede haber varios
                # documentos vigentes del mismo tipo, tenga o no
                # fecha el resto". Nunca se inventa SU fecha, solo se
                # usa que ya sabemos que no puede ser el vigente.
                if not entry.is_obsolete:
                    stats["filas_pasadas_a_obsoleto"] += 1
                    cambios.append((
                        "-> OBSOLETO", entry.pk, entry.name,
                        entry.expiry_date or entry.issue_date, max_date,
                    ))
                    grupo_cambio = True
                    if apply_changes:
                        entry.is_obsolete = True
                        entry.save(update_fields=["is_obsolete"])
            if grupo_cambio:
                stats["grupos_corregidos"] += 1

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self.stdout.write("    grupos con mas de un documento: %d" % groups.count())
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
        self.stdout.write("    cambios reales (hasta 80):")
        for tipo, pk, name, fecha, fecha_vigente in cambios[:80]:
            self.stdout.write(
                "        %s  pk=%d  %s  (fecha=%s, vigente real=%s)"
                % (tipo, pk, name, fecha, fecha_vigente)
            )

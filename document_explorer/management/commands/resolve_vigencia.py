# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/resolve_vigencia.py
"""
H30 (S50) -- resolucion real de vigencia cuando hay mas de un
DocumentIndexEntry no obsoleto del mismo document_type para el mismo
sujeto (MachineAsset o PersonIdentity).

Origen real: al desanidar la carpeta duplicada de A-59 (pk 607, S50)
aparecieron a la vista casos con mas de un "vigente" simultaneo del
mismo tipo (ITV, SEGURO...) -- el problema no lo causa la fusion, ya
existia repartido entre carpetas. Medido en todo el proyecto: 631
grupos (sujeto + tipo documental) con mas de un no-obsoleto a la vez.

Regla, verbatim de Miguel Angel (S50): "Si hay una ITV que caduca en
2026, otra que caduca en 2027 y otra que caduca en 2028, la vigente es
la que caduca en 2028 [...] no puede haber varios documentos vigentes
del mismo tipo de documento, a no ser que sean el mismo y tengan la
misma fecha." Fecha efectiva = expiry_date si existe (tipos con
caducidad clara), si no issue_date (tipos sin caducidad propia, el mas
reciente vale) -- mismo criterio de dos campos que ya usa el propio
modelo (ver DocumentIndexEntry.issue_date, H30 S045).

Blindaje anverso/reverso (S50, segunda pasada): al revisar los
empates se encontraron 3 casos reales previos a esta sesion donde un
archivo "REVERSO"/"ANVERSO" (misma pareja de dos caras de un mismo
documento fisico -- DNI, ficha tecnica, carnet de conducir) habia
quedado compitiendo contra su propio anverso como si fueran
versiones distintas del mismo documento, dejando el anverso marcado
obsoleto y solo el reverso vigente -- exactamente al reves de lo
util. Un reverso/anverso NUNCA es una version mas reciente ni mas
antigua de su pareja, es la otra cara del mismo documento fisico:
ambos deben poder quedar vigentes a la vez. Esta pasada nunca
compara ni marca obsoleto un miembro de un grupo si su nombre (o el
de su pareja) contiene "REVERSO"/"ANVERSO"/"REVERSI" -- los dos
lados quedan fuera de esta regla de fecha por completo, sea cual sea
la fecha que tengan o lleguen a tener.

Alcance real de esta primera pasada (medido en S50 antes de escribir
esto, ver EnterpriseBot_004_GET.txt de la sesion):
- 52 grupos resolubles sin ambiguedad: todos los miembros tienen fecha
  efectiva y las fechas difieren -- el de fecha mas reciente se queda
  vigente, el resto pasa a obsoleto.
- 132 grupos parciales: algunos miembros tienen fecha, otros no. Esta
  pasada SOLO marca obsoleto lo que es seguro marcar (un miembro con
  fecha real estrictamente anterior a otra fecha real del mismo grupo
  no puede ser el vigente, tenga o no fecha el resto). Nunca decide
  sobre miembros sin fecha -- quedan tal cual hasta que Fase B1/OCR les
  ponga fecha.
- 17 empates exactos de fecha: NUNCA los toca esta pasada (regla
  explicita de Miguel Angel, "hay que ver lo que hacemos, con cual nos
  quedamos" -- pendiente de decision propia, no de heuristica).
- 430 grupos sin ninguna fecha real en ningun miembro: fuera de
  alcance de esta pasada por completo, bloqueados hasta Fase B1/OCR.

DRY-RUN POR DEFECTO. Sin --apply, solo informa cuantos grupos entran
en cada categoria y cuantas filas se marcarian obsoletas. Con --apply,
escribe is_obsolete=True de verdad en las filas perdedoras -- nunca
toca blob_name/parent_path/name (4.12), nunca decide sobre empates ni
sobre miembros sin fecha.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Count

from document_explorer.models import DocumentIndexEntry


class Command(BaseCommand):
    help = (
        "H30 (S50) -- marca obsoletos los DocumentIndexEntry que no "
        "pueden ser el vigente de su grupo (sujeto + tipo documental) "
        "segun fecha efectiva. Dry-run por defecto, usar --apply para "
        "escribir de verdad. Nunca toca empates exactos ni grupos sin "
        "ninguna fecha."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help=(
                "Escribe is_obsolete=True de verdad en las filas "
                "perdedoras. Sin esta flag, solo informa."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        base = DocumentIndexEntry.objects.filter(
            entry_kind=DocumentIndexEntry.KIND_FILE,
            is_obsolete=False,
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
            "resueltos_sin_ambiguedad": 0,
            "parciales_con_algo_seguro": 0,
            "parciales_sin_nada_seguro": 0,
            "empates_exactos": 0,
            "bloqueados_sin_fecha": 0,
        }
        filas_marcadas = 0
        empates_para_revision = []

        for g in groups:
            entries = list(base.filter(
                domain_content_type_id=g["domain_content_type_id"],
                domain_object_id=g["domain_object_id"],
                document_type_id=g["document_type_id"],
            ))

            # Blindaje anverso/reverso (S50) -- si CUALQUIER miembro
            # del grupo es la otra cara de un documento fisico, todo
            # el grupo queda fuera de la regla de fecha. Nunca se
            # decide "vigente" entre un anverso y su propio reverso.
            if any(
                "REVERSO" in e.name.upper() or "ANVERSO" in e.name.upper()
                or "REVERSI" in e.name.upper()
                for e in entries
            ):
                stats["bloqueados_sin_fecha"] += 1
                continue

            dated = [
                (e, e.expiry_date or e.issue_date) for e in entries
                if e.expiry_date or e.issue_date
            ]
            undated = [e for e in entries if not e.expiry_date and not e.issue_date]

            if len(dated) < 2:
                # Ni un segundo punto de comparacion real -- no se
                # puede decidir nada por fecha en este grupo todavia.
                stats["bloqueados_sin_fecha"] += 1
                continue

            max_date = max(d for _, d in dated)
            winners = [e for e, d in dated if d == max_date]
            losers = [e for e, d in dated if d < max_date]

            if len(winners) > 1 and not losers:
                # Empate exacto entre TODOS los datados y sin nadie
                # por debajo -- exactamente el caso que Miguel Angel
                # pidio dejar aparte.
                stats["empates_exactos"] += 1
                empates_para_revision.append(
                    (g["domain_object_id"], g["document_type_id"],
                     [e.pk for e in winners])
                )
                continue

            if not undated:
                stats["resueltos_sin_ambiguedad"] += 1
            elif losers:
                stats["parciales_con_algo_seguro"] += 1
            else:
                stats["parciales_sin_nada_seguro"] += 1
                continue

            for entry in losers:
                filas_marcadas += 1
                self.stdout.write(
                    "%s  pk=%d obsoleto=True (perdedor, fecha=%s, "
                    "vigente real=%s)  sujeto=%s tipo=%s"
                    % (
                        "APLICADO" if apply_changes else "CANDIDATO",
                        entry.pk,
                        entry.expiry_date or entry.issue_date,
                        max_date,
                        g["domain_object_id"], g["document_type_id"],
                    )
                )
                if apply_changes:
                    entry.is_obsolete = True
                    entry.save(update_fields=["is_obsolete"])

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        self.stdout.write("    grupos con mas de un vigente: %d" % groups.count())
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
        self.stdout.write("    filas marcadas obsoletas: %d" % filas_marcadas)
        self.stdout.write("    empates pendientes de revision manual:")
        for machine_id, type_id, pks in empates_para_revision:
            self.stdout.write(
                "        sujeto=%s tipo=%s pks=%s" % (machine_id, type_id, pks)
            )

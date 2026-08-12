# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/resolve_itv_ficha_tecnica_dossier.py
"""
H30 (S50) -- resuelve el patron real de empate exacto de fecha entre
un ITV suelto y un documento combinado "FICHA TECNICA + ITV" del
mismo vehiculo/maquina, detectado al revisar los empates que
resolve_vigencia (S50) dejo fuera por regla explicita.

Regla, verbatim de Miguel Angel (S50): "lo primero que hay que ver es
si hay un combinado [...] tenemos ITV mas ficha tecnica, lo que hay
que ver es si ya existe ficha tecnica y si existe ITV. Si existen
ambos, el de ficha tecnica mas ITV es el que hay que eliminarlo [...]
Si tenemos ITV y ficha tecnica mas ITV, pero no tenemos ficha tecnica
[...] deberiamos de quedarnos con el de ficha tecnica mas ITV antes
que con el de ITV solo, siempre y cuando la fecha sea la vigente
tanto en ITV unitario como en el de ficha tecnica mas ITV."

Alcance deliberadamente estrecho -- solo actua cuando TODO esto es
cierto a la vez:
1. Grupo de exactamente 2 DocumentIndexEntry vivos, mismo sujeto,
   ambos document_type=ITV.
2. Exactamente uno de los dos tiene "FICHA" e "ITV" en el nombre (el
   combinado); el otro NO tiene "FICHA" en el nombre (el suelto).
3. Ambos comparten la misma fecha efectiva (expiry_date o
   issue_date) -- condicion explicita de Miguel Angel.

Nunca toca: grupos de 3 o mas (p.ej. Z-43, con un tercer "INFORME
INSPECCION ITV" ademas del combinado y el suelto -- fuera de esta
regla de dos ramas), pares donde ninguno lleva "FICHA" en el nombre
(p.ej. Z-105, "INFORME ITV" vs "ITV" -- no es el patron de dossier
descrito), ni fechas distintas (eso ya lo resuelve resolve_vigencia).

DRY-RUN POR DEFECTO. Con --apply escribe is_obsolete=True de verdad
en el perdedor de cada par resuelto -- nunca borra filas, nunca toca
GCS (4.12).
"""
from collections import defaultdict

from django.core.management.base import BaseCommand

from document_explorer.models import DocumentIndexEntry


class Command(BaseCommand):
    help = (
        "H30 (S50) -- resuelve el par ITV suelto vs FICHA TECNICA+ITV "
        "combinado en empates de fecha, segun si ya existe una "
        "FICHA_TECNICA suelta y viva para el mismo sujeto. Dry-run "
        "por defecto, usar --apply para escribir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe is_obsolete=True de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        base = DocumentIndexEntry.objects.filter(
            entry_kind=DocumentIndexEntry.KIND_FILE,
            is_obsolete=False,
            document_type__code="ITV",
            domain_object_id__isnull=False,
            deleted_at__isnull=True,
            purged_at__isnull=True,
        ).select_related("document_type")

        groups = defaultdict(list)
        for e in base:
            groups[(e.domain_content_type_id, e.domain_object_id)].append(e)

        stats = {
            "resueltos_ficha_ya_existe": 0,
            "resueltos_ficha_no_existe": 0,
            "fuera_de_alcance_no_2": 0,
            "fuera_de_alcance_sin_patron": 0,
            "fuera_de_alcance_fecha_distinta": 0,
        }
        fuera_de_alcance_detalle = []

        for (ct_id, obj_id), entries in groups.items():
            if len(entries) != 2:
                if len(entries) > 1:
                    stats["fuera_de_alcance_no_2"] += 1
                    fuera_de_alcance_detalle.append(
                        ("grupo != 2", obj_id, [e.pk for e in entries])
                    )
                continue

            combinados = [
                e for e in entries
                if "FICHA" in e.name.upper() and "ITV" in e.name.upper()
            ]
            sueltos = [e for e in entries if "FICHA" not in e.name.upper()]

            if len(combinados) != 1 or len(sueltos) != 1 or combinados[0] == sueltos[0]:
                stats["fuera_de_alcance_sin_patron"] += 1
                fuera_de_alcance_detalle.append(
                    ("sin patron ficha+itv", obj_id, [(e.pk, e.name) for e in entries])
                )
                continue

            combinado = combinados[0]
            suelto = sueltos[0]
            fecha_combinado = combinado.expiry_date or combinado.issue_date
            fecha_suelto = suelto.expiry_date or suelto.issue_date
            if fecha_combinado != fecha_suelto:
                stats["fuera_de_alcance_fecha_distinta"] += 1
                continue

            ficha_tecnica_viva = DocumentIndexEntry.objects.filter(
                domain_content_type_id=ct_id, domain_object_id=obj_id,
                document_type__code="FICHA_TECNICA",
                entry_kind=DocumentIndexEntry.KIND_FILE,
                is_obsolete=False,
                deleted_at__isnull=True, purged_at__isnull=True,
            ).exists()

            if ficha_tecnica_viva:
                perdedor, ganador = combinado, suelto
                stats["resueltos_ficha_ya_existe"] += 1
                motivo = "FICHA_TECNICA suelta ya existe -- combinado sobra"
            else:
                perdedor, ganador = suelto, combinado
                stats["resueltos_ficha_no_existe"] += 1
                motivo = "no hay FICHA_TECNICA suelta -- se queda el combinado"

            self.stdout.write(
                "%s  sujeto=%s | perdedor pk=%d (%s) -> obsoleto=True | "
                "vigente pk=%d (%s) | %s"
                % (
                    "APLICADO" if apply_changes else "CANDIDATO",
                    obj_id, perdedor.pk, perdedor.name,
                    ganador.pk, ganador.name, motivo,
                )
            )
            if apply_changes:
                perdedor.is_obsolete = True
                perdedor.save(update_fields=["is_obsolete"])

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in stats.items():
            self.stdout.write("    %s: %d" % (key, value))
        self.stdout.write("    fuera de alcance, detalle:")
        for motivo, obj_id, detalle in fuera_de_alcance_detalle:
            self.stdout.write("        [%s] sujeto=%s %s" % (motivo, obj_id, detalle))

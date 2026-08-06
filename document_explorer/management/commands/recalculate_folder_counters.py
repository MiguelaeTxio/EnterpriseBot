# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/recalculate_folder_counters.py
"""
Django management command: recalculate_folder_counters.

H29, S042 -- Miguel Ángel, con datos reales del propio panel
("MANUALES DE USO" decía 215 elementos desde el listado padre, pero
al entrar solo había 196 filas de verdad; varias carpetas mostraban
tamaños NEGATIVOS, algo físicamente imposible): "Hay que ver la
aplicación entera... no puede ser que en una carpeta hay cuatro
archivos, que entres luego a la carpeta y que te diga que hay uno."

Diagnóstico confirmado antes de escribir una sola línea de este
comando (método empírico, nunca bola de cristal): de 3757 carpetas
vivas en el cubo histórico, 946 (una de cada cuatro) tienen
`child_count` desajustado frente al recuento real de sus hijos
directos vivos, y 318 tienen `total_size_bytes` NEGATIVO -- la mayor
deriva, `_CUARENTENA/DOC. MAQUINAS`, acumula -46,7 GB de más restados.
La magnitud (cientos de carpetas, decenas de GB) indica una deriva
acumulada de mucho antes de esta sesión, no un fallo puntual de hoy --
`_adjust_child_count()`/`_adjust_total_size()` (`move_service.py`)
corrigen bien un movimiento AISLADO, pero cualquier operación que
alguna vez haya escrito `parent_path`/`blob_name`/`deleted_at` sin
pasar por esas dos funciones (o una condición de carrera entre varias
Always-on Tasks corriendo a la vez) deja detrás una diferencia que
nunca se corrige sola -- son contadores denormalizados, no vistas
calculadas, así que la deriva se acumula silenciosamente para
siempre hasta que alguien la mide y la corrige.

Recalcula ambos campos desde cero para TODAS las carpetas vivas de un
cubo, a partir de los datos reales (nunca de otros contadores ya
sospechosos):

- `child_count`: recuento SQL directo de filas vivas (archivo o
  carpeta) cuyo `parent_path` sea exactamente la propia carpeta --
  documentado en el propio modelo como "solo hijos DIRECTOS".
- `total_size_bytes`: recursivo por definición (mismo docstring de
  `DocumentIndexEntry`) -- se calcula de abajo hacia arriba en una
  sola pasada en memoria (todas las carpetas del cubo caben de sobra,
  unos pocos miles de filas): para cada carpeta, tamaño de sus
  archivos directos + el total YA calculado de cada subcarpeta directa
  viva, procesando siempre las carpetas más profundas primero. Un
  único recorrido, sin repetir sobre el mismo subárbol una y otra vez
  como haría una suma recursiva ingenua carpeta a carpeta.

Nunca toca GCS ni `blob_name` de ningún archivo -- pura corrección de
dos campos cacheados en filas de carpeta, mismo principio de "clasificar/
mover nunca toca GCS" del resto del módulo (H29 3.19/4.12).

Por defecto ESCRIBE de verdad (mismo criterio que `seed_person_
identities`/`repair_reverted_quarantine_relocations`) -- usar
`--dry-run` para ver el informe completo sin escribir nada.

Uso:
    python -m dotenv run python manage.py \
        recalculate_folder_counters --bucket cgs_grupo_alvarez --dry-run
    python -m dotenv run python manage.py \
        recalculate_folder_counters --bucket cgs_grupo_alvarez
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, Sum

from document_explorer.models import DocumentIndexEntry


class Command(BaseCommand):
    help = (
        "Recalcula child_count y total_size_bytes de TODAS las "
        "carpetas vivas de un cubo desde los datos reales -- "
        "corrige la deriva acumulada de estos contadores "
        "denormalizados (H29, S042, hallazgo real de Miguel Ángel)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--bucket",
            required=True,
            help="Cubo indexado a recalcular (obligatorio).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo informa qué se corregiría, sin escribir nada.",
        )

    def handle(self, *args, **options):
        bucket = options["bucket"]
        dry_run = options["dry_run"]

        folders = list(
            DocumentIndexEntry.objects.filter(
                bucket=bucket, entry_kind=DocumentIndexEntry.KIND_FOLDER,
                deleted_at__isnull=True, purged_at__isnull=True,
            )
        )
        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== %d carpeta(s) viva(s) en el cubo %s ===" % (
                len(folders), bucket,
            )
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "Dry-run: no se escribirá nada."
            ))

        # child_count real: filas vivas (archivo o carpeta) agrupadas
        # por su parent_path -- una sola consulta para todo el cubo.
        real_child_counts = dict(
            DocumentIndexEntry.objects.filter(
                bucket=bucket,
                deleted_at__isnull=True, purged_at__isnull=True,
            )
            .values("parent_path")
            .annotate(n=Count("pk"))
            .values_list("parent_path", "n")
        )

        # Tamaño de los archivos DIRECTOS de cada carpeta -- punto de
        # partida del cálculo recursivo de abajo hacia arriba.
        direct_file_size = dict(
            DocumentIndexEntry.objects.filter(
                bucket=bucket, entry_kind=DocumentIndexEntry.KIND_FILE,
                deleted_at__isnull=True, purged_at__isnull=True,
            )
            .values("parent_path")
            .annotate(s=Sum("size_bytes"))
            .values_list("parent_path", "s")
        )

        # Subcarpetas directas vivas de cada carpeta, para poder subir
        # el total ya calculado de cada una a su padre en una sola
        # pasada, sin repetir el mismo subárbol una y otra vez.
        child_folders_by_parent = {}
        for f in folders:
            child_folders_by_parent.setdefault(f.parent_path, []).append(
                f.blob_name,
            )

        real_total_size = {}
        for f in sorted(
            folders, key=lambda x: x.blob_name.count("/"), reverse=True,
        ):
            total = direct_file_size.get(f.blob_name, 0) or 0
            for child_path in child_folders_by_parent.get(f.blob_name, []):
                total += real_total_size.get(child_path, 0)
            real_total_size[f.blob_name] = total

        to_update = []
        child_count_diffs = 0
        size_diffs = 0
        for f in folders:
            new_child_count = real_child_counts.get(f.blob_name, 0)
            new_total_size = real_total_size.get(f.blob_name, 0)
            changed = False
            if new_child_count != f.child_count:
                child_count_diffs += 1
                changed = True
            if new_total_size != f.total_size_bytes:
                size_diffs += 1
                changed = True
            if changed:
                self.stdout.write(
                    "[CORREGIR] %s -- child_count %d -> %d, "
                    "total_size_bytes %d -> %d" % (
                        f.blob_name, f.child_count, new_child_count,
                        f.total_size_bytes, new_total_size,
                    )
                )
                f.child_count = new_child_count
                f.total_size_bytes = new_total_size
                to_update.append(f)

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== RESUMEN ==="))
        self.stdout.write(
            "Carpetas con child_count desajustado: %d" % child_count_diffs
        )
        self.stdout.write(
            "Carpetas con total_size_bytes desajustado: %d" % size_diffs
        )
        self.stdout.write(
            "Carpetas a corregir en total: %d de %d" % (
                len(to_update), len(folders),
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "Dry-run: nada de lo anterior se ha escrito de verdad."
            ))
            return

        if to_update:
            DocumentIndexEntry.objects.bulk_update(
                to_update, ["child_count", "total_size_bytes"],
                batch_size=500,
            )
        self.stdout.write(self.style.SUCCESS(
            "%d carpeta(s) corregida(s) de verdad." % len(to_update)
        ))

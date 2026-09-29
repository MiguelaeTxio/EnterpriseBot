# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/link_personal_folder_entries.py
"""
H30 (S124), roadmap item 2. Repairs files already filed under
DOC. PERSONAL/PERSONAL/ by the quarantine pipeline without owner or
type (the defect fixed in item 1).

---

H30 (S124), punto 2 de la hoja de ruta. Repara lo que el pipeline de
cuarentena ya archivó en DOC. PERSONAL/PERSONAL/ sin persona ni tipo
(el defecto corregido en el punto 1):

- Persona: la PersonIdentity cuyo `folder_path` es EXACTAMENTE la
  carpeta del archivo. Nunca por nombre ni por aproximación.
- Tipo: el que dice su nombre canónico
  `APELLIDOS_NOMBRE_{TIPO}_{AAAAMMDD}[_N].ext` (el código de catálogo
  más largo en que termina el nombre sin fecha ni ordinal). Si el
  nombre no es canónico, el archivo se vincula igual y queda sin tipo,
  listado con su motivo. Un archivo que ya tiene tipo lo conserva.
- Lo que no tiene carpeta de dueño se lista con su motivo, sin tocar.

No activa a nadie (eso es el punto 3), no renombra ni mueve nada.

DRY-RUN POR DEFECTO. `--apply` escribe. `--log-file` obligatorio: log
propio en pantalla y en archivo a la vez.
"""
import re
from collections import Counter
from datetime import datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity,
)
from document_explorer.naming_service import _sanitize_token

BUCKET = "cgs_grupo_alvarez"
SCOPE_ROOT = "DOC. PERSONAL/PERSONAL/"
HEARTBEAT_EVERY = 25

# Nombre canónico sin extensión: prefijo + fecha + ordinal opcional.
_CANONICAL_STEM_RE = re.compile(
    r"^(?P<prefix>.+)_(?P<date>\d{8})(?:_(?P<ordinal>\d+))?$"
)


def person_prefix(identity):
    """
    Canonical surnames/name prefix of a person's file names.

    ---

    Prefijo canónico (apellidos y nombre) de los archivos de la persona,
    con el mismo saneado que `naming_service`.
    """
    tokens = [
        _sanitize_token(part) for part in (
            identity.first_surname, identity.second_surname,
            identity.given_name,
        )
    ]
    return "_".join(token for token in tokens if token)


def type_code_from_name(name, codes_longest_first):
    """
    Return (code, prefix_before_code) read off a canonical name.

    ---

    Devuelve (código, prefijo anterior al código) leídos de un nombre
    canónico, o (None, None) si el nombre no lo es.
    """
    stem = name.rsplit(".", 1)[0] if "." in name else name
    match = _CANONICAL_STEM_RE.match(stem)
    if not match:
        return None, None
    prefix = match.group("prefix")
    for code in codes_longest_first:
        if prefix.endswith("_" + code):
            return code, prefix[:-(len(code) + 1)]
    return None, None


class Command(BaseCommand):
    """
    Link and type PERSONAL files left without owner by quarantine.

    ---

    Vincula y tipa los archivos de PERSONAL que la cuarentena dejó sin
    dueño.
    """

    help = (
        "Vincula a su persona (por carpeta) y tipa (por nombre canónico) "
        "los archivos de DOC. PERSONAL/PERSONAL/ sin persona (H30, "
        "S124). Dry-run por defecto; --apply escribe."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, message):
        """
        Print and append one timestamped line to the log, flushed.

        ---

        Escribe una línea con hora en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def _log_plain(self, message):
        """
        Print and append one line without timestamp (final summary).

        ---

        Igual que `_log`, sin hora (resumen final, com-standards 0ter).
        """
        print(message, flush=True)
        self._log_handle.write(message + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._log_handle = handle
            self._run(apply_changes)

    def _run(self, apply_changes):
        """
        Main sweep.

        ---

        Barrido principal.
        """
        person_ct = ContentType.objects.get_for_model(PersonIdentity)
        catalog = {
            item.code: item for item in DocumentTypeCatalog.objects.all()
        }
        codes_longest_first = sorted(catalog, key=len, reverse=True)
        people_by_folder = {
            identity.folder_path.strip("/"): identity
            for identity in PersonIdentity.objects.exclude(
                folder_path__isnull=True,
            ).exclude(folder_path="")
        }

        entries = list(DocumentIndexEntry.objects.filter(
            bucket=BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            domain_object_id__isnull=True,
            parent_path__startswith=SCOPE_ROOT,
        ).select_related("document_type").order_by("parent_path", "id"))

        total = len(entries)
        self._log(
            "Modo: %s -- %d archivos de %s sin persona."
            % ("APPLY" if apply_changes else "DRY-RUN", total, SCOPE_ROOT)
        )

        stats = Counter()
        orphan_folders = Counter()
        start = datetime.now()

        for index, entry in enumerate(entries, start=1):
            identity = people_by_folder.get(entry.parent_path)
            if identity is None:
                stats["sin_carpeta_de_dueno"] += 1
                orphan_folders[entry.parent_path] += 1
                self._log(
                    "SIN DUEÑO #%d %s -- motivo: ninguna persona tiene "
                    "la carpeta %s" % (entry.pk, entry.name, entry.parent_path)
                )
            else:
                self._handle_entry(
                    entry, identity, person_ct, catalog,
                    codes_longest_first, apply_changes, stats,
                )

            if index % HEARTBEAT_EVERY == 0 or index == total:
                elapsed = (datetime.now() - start).total_seconds()
                eta_seg = (elapsed / index) * (total - index)
                end_at = datetime.now() + timedelta(seconds=eta_seg)
                self._log(
                    "Progreso: %d/%d (%d%%) -- ETA %dm%02ds (fin aprox. %s)"
                    " -- vinculados=%d, con_tipo=%d, sin_dueno=%d"
                    % (
                        index, total, index * 100 // total,
                        eta_seg // 60, eta_seg % 60,
                        end_at.strftime("%H:%M:%S"),
                        stats["vinculados"], stats["tipo_por_nombre"],
                        stats["sin_carpeta_de_dueno"],
                    )
                )

        self._log_plain("")
        self._log_plain("RESUMEN (%s)" % (
            "APPLY" if apply_changes else "DRY-RUN"
        ))
        self._log_plain("  Archivos sin persona: %d" % total)
        for key in (
            "vinculados", "tipo_por_nombre", "tipo_ya_existente",
            "nombre_no_canonico", "prefijo_de_otra_persona",
            "sin_carpeta_de_dueno",
        ):
            self._log_plain("  %s: %d" % (key, stats[key]))
        if orphan_folders:
            self._log_plain("  Carpetas sin dueño:")
            for folder, count in orphan_folders.most_common():
                self._log_plain("    %4d  %s" % (count, folder))

    def _handle_entry(
        self, entry, identity, person_ct, catalog, codes_longest_first,
        apply_changes, stats,
    ):
        """
        Link one entry to its folder owner and type it by name.

        ---

        Vincula una entrada al dueño de su carpeta y la tipa por nombre.
        """
        code, prefix = type_code_from_name(entry.name, codes_longest_first)
        fields = ["domain_content_type", "domain_object_id", "updated_at"]
        note = ""
        if entry.document_type_id:
            stats["tipo_ya_existente"] += 1
            note = "tipo ya existente %s" % entry.document_type.code
        elif code:
            stats["tipo_por_nombre"] += 1
            entry.document_type = catalog[code]
            fields.append("document_type")
            note = "tipo %s" % code
            if prefix != person_prefix(identity):
                stats["prefijo_de_otra_persona"] += 1
                note += " (AVISO: el nombre empieza por %s, la carpeta es " \
                    "de %s)" % (prefix, person_prefix(identity))
        else:
            stats["nombre_no_canonico"] += 1
            note = "sin tipo -- motivo: nombre no canónico"

        entry.domain_content_type = person_ct
        entry.domain_object_id = identity.pk
        stats["vinculados"] += 1
        if apply_changes:
            entry.save(update_fields=fields)
        self._log(
            "VINCULADO #%d %s -> persona %d -- %s"
            % (entry.pk, entry.name, identity.pk, note)
        )

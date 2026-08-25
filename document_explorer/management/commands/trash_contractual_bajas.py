# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/trash_contractual_bajas.py
"""
H30 (S68) -- manda a papelera los archivos de baja CONTRACTUAL real
(persona que ya no trabaja aqui), viviendo bajo
`DOC. PERSONAL/PERSONAL/BAJAS/`.

Distincion real confirmada por Miguel Angel en S68, tras encontrar tres
carpetas distintas bajo el nombre "BAJAS" que no significan lo mismo:

1. `DOC. PERSONAL/PERSONAL/OPERARIOS/<persona>/<persona>/BAJAS/...`
   -- baja de incapacidad laboral transitoria (ILT) de un trabajador
   ACTIVO, archivada dentro de su propia carpeta. Nunca se toca aqui
   -- ni siquiera se consulta, queda fuera del alcance de este comando
   por construccion (nunca se lee `OPERARIOS/`, solo `BAJAS/`).
2. `DOC. PERSONAL/PERSONAL/BAJAS/BAJA PERSONAL/<persona>/...`
   -- TAMBIEN es ILT (verbatim Miguel Angel: "baja personal son
   incapacidades laborales transitorias"), solo que mal archivada
   fuera de la carpeta del operario -- pendiente de un comando aparte
   que las reubique en su OPERARIOS/<persona>/ real, nunca papelera.
   Este comando NUNCA toca esta rama.
3. `DOC. PERSONAL/PERSONAL/BAJAS/OPERARIOS BAJAS/<persona>/...` y los
   archivos sueltos `DOC. PERSONAL/PERSONAL/BAJAS/BAJA <apellidos>.pdf`
   -- estas si son bajas CONTRACTUALES reales (la empresa, no el
   trabajador). Miguel Angel, verbatim: "Operarios bajas es para
   eliminar." Es el UNICO alcance real de este comando.

Criterio de coincidencia con activos -- CORREGIDO en la misma sesion
tras un error real de diseño propio: comparar solo apellidos (pareja)
o un solapamiento parcial de tokens (>= 66%) genera falsos positivos
reales (p. ej. "CABELLO SANCHEZ, FRANCISCO" solapaba con el activo
"ROSAS SANCHEZ FRANCISCO JOSE" solo por compartir "SANCHEZ FRANCISCO",
sin ser ni siquiera el mismo primer apellido). Miguel Angel, verbatim:
"si no coincide el otro apellido, no son la misma persona [...] vamos
a estar un poco centrados en lo que estamos haciendo." Regla real:
todos los tokens (apellidos + nombre) de la carpeta deben estar
CONTENIDOS en la identidad completa de un activo real -- subconjunto
estricto, nunca solapamiento parcial. Ambiguedad real (revision manual,
nunca se aplica aqui) solo existe cuando la propia carpeta no trae
nombre de pila y hay mas de un activo con esos dos apellidos -- caso
que no se ha dado todavia en los datos reales de S68, pero el
comando lo deja fuera del alcance de --apply si llega a aparecer
(unico_activo=False).

Principio 4.12 respetado: usa `trash_dossier_entry()` (deleted_at/
deleted_by, escritura de indice pura) -- `blob_name` en GCS nunca se
toca.

DRY-RUN POR DEFECTO. Con --apply manda a papelera de verdad.
"""
import os
import re

from django.core.management.base import BaseCommand

from document_explorer.classification_service import trash_dossier_entry
from document_explorer.models import DocumentIndexEntry, PersonIdentity

ROOT_OPERARIOS_BAJAS = "DOC. PERSONAL/PERSONAL/BAJAS/OPERARIOS BAJAS/"
ROOT_BAJAS_DIRECTAS = "DOC. PERSONAL/PERSONAL/BAJAS"

_PAREN_RE = re.compile(r"\([^)]*\)")


def _tokens(texto):
    sin_parentesis = _PAREN_RE.sub(" ", texto)
    sin_parentesis = sin_parentesis.replace(",", " ").replace(".", " ")
    return set(
        t for t in re.split(r"\s+", sin_parentesis.strip().upper())
        if len(t) > 1 and t != "NUEVO"
    )


def _clasificar(nombre, activos_tokens):
    """
    Devuelve (es_activo, pk_activo) -- es_activo=True solo si TODOS los
    tokens de `nombre` estan contenidos en la identidad completa de
    exactamente un activo real (subconjunto estricto, nunca
    solapamiento parcial -- ver docstring del modulo).
    """
    t = _tokens(nombre)
    if not t:
        return False, None
    candidatos = [
        (pk, full) for pk, full, at in activos_tokens
        if at and t.issubset(at)
    ]
    if len(candidatos) == 1:
        return True, candidatos[0]
    if len(candidatos) > 1:
        # Ambiguedad real: mas de un activo cuya identidad contiene
        # estos tokens. Nunca se decide sola -- se trata como si
        # coincidiera (no se manda a papelera) para forzar revision
        # manual explicita.
        return True, None
    return False, None


class Command(BaseCommand):
    help = (
        "H30 (S68) -- manda a papelera las bajas CONTRACTUALES reales "
        "(OPERARIOS BAJAS + archivos directos BAJA *.pdf bajo "
        "DOC. PERSONAL/PERSONAL/BAJAS/), excluyendo BAJA PERSONAL (ILT, "
        "fuera de alcance) y cualquier carpeta cuya identidad completa "
        "coincida con un trabajador activo real. Dry-run por defecto, "
        "--apply para escribir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        activos = list(
            PersonIdentity.objects.filter(is_active_employee=True)
            .values_list("id", "first_surname", "second_surname", "given_name")
        )
        activos_tokens = []
        for pk, fs, ss, gn in activos:
            full = "%s %s %s" % (fs, ss or "", gn)
            activos_tokens.append((pk, full.strip(), _tokens(full)))

        totales = {"candidatos": 0, "a_papelera": 0, "fallos": 0, "retenidos": 0}

        # --- 1) OPERARIOS BAJAS/<persona>/... ---
        qs_op = DocumentIndexEntry.objects.filter(
            bucket="cgs_grupo_alvarez",
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
            parent_path__startswith=ROOT_OPERARIOS_BAJAS,
        ).only("id", "parent_path", "name")

        for entry in qs_op.iterator():
            resto = entry.parent_path[len(ROOT_OPERARIOS_BAJAS):]
            carpeta = resto.split("/")[0] if resto else ""
            es_activo, quien = _clasificar(carpeta, activos_tokens)
            totales["candidatos"] += 1
            if es_activo:
                totales["retenidos"] += 1
                self.stdout.write(
                    "RETENIDO (coincide con activo%s): %s / %s"
                    % (" -- %s" % quien[1] if quien else " -- AMBIGUO, revisar a mano",
                       entry.parent_path, entry.name)
                )
                continue
            if apply_changes:
                ok = trash_dossier_entry(entry)
                if ok:
                    totales["a_papelera"] += 1
                else:
                    totales["fallos"] += 1
                    self.stdout.write("FALLO: %s / %s" % (entry.parent_path, entry.name))
            else:
                self.stdout.write("IRIA A PAPELERA: %s / %s" % (entry.parent_path, entry.name))

        # --- 2) Archivos directos "BAJA <apellidos>.pdf" bajo BAJAS/ (nunca BAJA PERSONAL/) ---
        qs_directos = DocumentIndexEntry.objects.filter(
            bucket="cgs_grupo_alvarez",
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True,
            purged_at__isnull=True,
            parent_path=ROOT_BAJAS_DIRECTAS,
        ).only("id", "name")

        for entry in qs_directos.iterator():
            # Bug real detectado en dry-run S68: dejar la extension
            # (".pdf") pegada al nombre generaba un token suelto "PDF"
            # que rompia la coincidencia exacta por subconjunto contra
            # la identidad del activo -- ver _clasificar(). Se quita
            # la extension antes de tokenizar.
            nombre_persona, _ext = os.path.splitext(entry.name)
            if nombre_persona.upper().startswith("BAJA "):
                nombre_persona = nombre_persona[5:]
            es_activo, quien = _clasificar(nombre_persona, activos_tokens)
            totales["candidatos"] += 1
            if es_activo:
                totales["retenidos"] += 1
                self.stdout.write(
                    "RETENIDO (coincide con activo%s): %s / %s"
                    % (" -- %s" % quien[1] if quien else " -- AMBIGUO, revisar a mano",
                       entry.parent_path, entry.name)
                )
                continue
            if apply_changes:
                ok = trash_dossier_entry(entry)
                if ok:
                    totales["a_papelera"] += 1
                else:
                    totales["fallos"] += 1
                    self.stdout.write("FALLO: %s / %s" % (entry.parent_path, entry.name))
            else:
                self.stdout.write("IRIA A PAPELERA: %s / %s" % (entry.parent_path, entry.name))

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for key, value in totales.items():
            self.stdout.write("    %s: %d" % (key, value))

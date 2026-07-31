# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/naming_service.py
"""
Deterministic renaming engine for H29 (S040).

Gemini's job stops at *suggesting* a `DocumentTypeCatalog.code` (and,
where relevant, the machine code / person name it read off the
document). Building the actual filename is always this module's job,
never Gemini's own wording -- Miguel Angel, S040: a free-form name
from Gemini would drift in format over time; a dedicated, deterministic
method never does.

Two formats only, both confirmed verbatim by Miguel Angel in S040:

- Machine:  {MACHINE_CODE}_{DOCUMENT_TYPE_CODE}_{DATE}.pdf
- Personal: {SURNAME}_{GIVEN_NAME}_{DOCUMENT_TYPE_CODE}_{DATE}.pdf
  (never by DNI or any numeric identifier -- explicitly rejected by
  Miguel Angel: "para los trabajadores lo que nos sirve es apellido,
  nombre, tipo de documento y fecha, para que cuando estés mirando el
  archivo sepas perfectamente de quién estás hablando").

Date format: `%Y%m%d` (compact, no separators of its own, consistent
with the only other filename-timestamp precedent in this repo --
`h28_migration_agent/auditor.py`).

---

Motor de renombrado determinista para H29 (S040).

El trabajo de Gemini termina en *sugerir* un `DocumentTypeCatalog.code`
(y, cuando aplique, el código de máquina / nombre de persona que haya
leído en el documento). Construir el nombre de archivo final es
siempre trabajo de este módulo, nunca la redacción propia de Gemini --
Miguel Ángel, S040: un nombre libre de Gemini derivaría de formato con
el tiempo; un método propio y determinista, nunca.

Dos formatos únicamente, ambos confirmados verbatim por Miguel Ángel
en S040:

- Máquina:  {CÓDIGO_MÁQUINA}_{CÓDIGO_TIPO_DOCUMENTO}_{FECHA}.pdf
- Personal: {APELLIDO}_{NOMBRE}_{CÓDIGO_TIPO_DOCUMENTO}_{FECHA}.pdf
  (nunca por DNI ni identificador numérico -- rechazado explícitamente
  por Miguel Ángel: "para los trabajadores lo que nos sirve es
  apellido, nombre, tipo de documento y fecha, para que cuando estés
  mirando el archivo sepas perfectamente de quién estás hablando").

Formato de fecha: `%Y%m%d` (compacto, sin separadores propios,
coherente con el único precedente real de timestamp en nombre de
archivo de este repo -- `h28_migration_agent/auditor.py`).
"""
import datetime
import re
import unicodedata

_INVALID_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9]+")


def _sanitize_token(value: str) -> str:
    """
    Normalise a name/code fragment for use inside a generated filename.

    Strips accents, uppercases, and collapses anything that is not a
    letter or digit into a single underscore -- so "Núñez López"
    becomes "NUNEZ_LOPEZ" and never breaks the fixed-format contract
    with a stray space, comma or accented character.

    ---

    Normaliza un fragmento de nombre/código para usarlo dentro de un
    nombre de archivo generado.

    Quita acentos, pasa a mayúsculas, y colapsa cualquier cosa que no
    sea letra o dígito en un único guion bajo -- así "Núñez López"
    queda "NUNEZ_LOPEZ" y nunca rompe el formato fijo por un espacio,
    una coma o un carácter acentuado sueltos.
    """
    normalised = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    collapsed = _INVALID_FILENAME_CHARS.sub("_", ascii_only).strip("_")
    return collapsed.upper()


def build_filename_machine(
    machine_code: str,
    document_type_code: str,
    date: datetime.date,
    extension: str = "pdf",
) -> str:
    """
    Build the fixed-format filename for a MACHINE-domain document.

    ---

    Construye el nombre de archivo de formato fijo para un documento
    de dominio MÁQUINA.
    """
    parts = [
        _sanitize_token(machine_code),
        _sanitize_token(document_type_code),
        date.strftime("%Y%m%d"),
    ]
    return "_".join(parts) + f".{extension.lstrip('.').lower()}"


def build_filename_personal(
    surname: str,
    given_name: str,
    document_type_code: str,
    date: datetime.date,
    extension: str = "pdf",
) -> str:
    """
    Build the fixed-format filename for a PERSONAL-domain document.

    Deliberately surname/given-name based, never DNI or any numeric
    identifier -- see module docstring.

    ---

    Construye el nombre de archivo de formato fijo para un documento
    de dominio PERSONAL.

    Deliberadamente basado en apellido/nombre, nunca en DNI ni
    identificador numérico -- ver docstring del módulo.
    """
    parts = [
        _sanitize_token(surname),
        _sanitize_token(given_name),
        _sanitize_token(document_type_code),
        date.strftime("%Y%m%d"),
    ]
    return "_".join(parts) + f".{extension.lstrip('.').lower()}"

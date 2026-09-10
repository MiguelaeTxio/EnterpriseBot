# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/naming_service.py
"""
Deterministic renaming engine for H29 (S040).

Gemini's job stops at *suggesting* a `DocumentTypeCatalog.code`.
Building the actual filename is always this module's job, never
Gemini's own wording -- Miguel Angel, S040: a free-form name from
Gemini would drift in format over time; a dedicated, deterministic
method never does.

Two formats only, both confirmed verbatim by Miguel Angel in S040,
**personal format revised same session** after seeing how badly a
person's name drifts across real filenames (H28 annex, Hallazgo 5: the
same operator's name spelled eight different ways, typos included):

- Machine:  {MACHINE_CODE}_{DOCUMENT_TYPE_CODE}_{DATE}[_{ORDINAL}].pdf
- Personal: {FIRST_SURNAME}_{SECOND_SURNAME}_{GIVEN_NAME}_{DOCUMENT_TYPE_CODE}_{DATE}[_{ORDINAL}].pdf

**Source of truth for the personal name is the person's own DNI
document content, never the source filename** -- Miguel Angel, S040:
"Tenemos que sacar los nombres y apellidos del DNI. No hay otra. En el
DNI viene nombre por un lado y apellidos por otro. Viene, es más,
viene como primer apellido, segundo apellido y nombre." This module
only builds the string from already-resolved name components; where
those components come from (DNI extraction) is the classification
engine's job, not this one's.

Why surname-first for people and code-first for machines, same
underlying reason for both -- Miguel Angel, S040: "si sacamos diversos
documentos de diversos trabajadores y los metemos en una carpeta, van
a quedar perfectamente ordenados por trabajador (...) si formamos un
dossier para enviarlo a alguna otra empresa, ese mismo orden nos va a
ayudar a que los PDFs del dossier (...) estén también ordenadas de
forma correcta." Plain alphabetical filename sort keeps every
person's/machine's documents grouped together even outside the
explorer's own folders (a flat dump, a mailed dossier, a zip export).

Optional trailing ordinal, for real collisions (same person/machine,
same type, same date) -- Miguel Angel, S040: "...fecha y ordinal por
si hay varios documentos que se llamen igual o que tengan la misma
fecha." Callers pass it only when a collision is actually detected;
this module never invents one on its own.

Date format: `%Y%m%d` (compact, no separators of its own, consistent
with the only other filename-timestamp precedent in this repo --
`h28_migration_agent/auditor.py`).

---

Motor de renombrado determinista para H29 (S040).

El trabajo de Gemini termina en *sugerir* un `DocumentTypeCatalog.code`.
Construir el nombre de archivo final es siempre trabajo de este
módulo, nunca la redacción propia de Gemini -- Miguel Ángel, S040: un
nombre libre de Gemini derivaría de formato con el tiempo; un método
propio y determinista, nunca.

Dos formatos únicamente, ambos confirmados verbatim por Miguel Ángel
en S040, **formato personal revisado en la misma sesión** al ver lo
mal que deriva el nombre de una persona entre nombres de archivo
reales (anexo H28, Hallazgo 5: el nombre del mismo operario escrito de
ocho formas distintas, con errores incluidos):

- Máquina:  {CÓDIGO_MÁQUINA}_{CÓDIGO_TIPO_DOCUMENTO}_{FECHA}[_{ORDINAL}].pdf
- Personal: {PRIMER_APELLIDO}_{SEGUNDO_APELLIDO}_{NOMBRE}_{CÓDIGO_TIPO_DOCUMENTO}_{FECHA}[_{ORDINAL}].pdf

**La fuente de verdad del nombre personal es el contenido real del
propio DNI de la persona, nunca el nombre de archivo de origen** --
Miguel Ángel, S040: "Tenemos que sacar los nombres y apellidos del
DNI. No hay otra. En el DNI viene nombre por un lado y apellidos por
otro. Viene, es más, viene como primer apellido, segundo apellido y
nombre." Este módulo solo construye la cadena a partir de componentes
de nombre ya resueltos; de dónde salen esos componentes (extracción
del DNI) es trabajo del motor de clasificación, no de este módulo.

Por qué apellidos primero para personas y código primero para
máquinas, mismo motivo de fondo en los dos casos -- Miguel Ángel,
S040: "si sacamos diversos documentos de diversos trabajadores y los
metemos en una carpeta, van a quedar perfectamente ordenados por
trabajador (...) si formamos un dossier para enviarlo a alguna otra
empresa, ese mismo orden nos va a ayudar a que los PDFs del dossier
(...) estén también ordenadas de forma correcta." El orden alfabético
llano del nombre de archivo mantiene agrupados los documentos de cada
persona/máquina incluso fuera de las carpetas del explorador (un
volcado plano, un dossier enviado por correo, un zip exportado).

Ordinal final opcional, para colisiones reales (misma persona/máquina,
mismo tipo, misma fecha) -- Miguel Ángel, S040: "...fecha y ordinal por
si hay varios documentos que se llamen igual o que tengan la misma
fecha." Quien llame a este módulo solo lo pasa cuando detecta una
colisión real; este módulo nunca se inventa uno por su cuenta.

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


def _build_filename(parts, date, ordinal, extension):
    """
    Shared assembly: sanitised parts + date + optional ordinal + extension.

    ---

    Ensamblado compartido: partes saneadas + fecha + ordinal opcional
    + extensión.
    """
    tokens = [_sanitize_token(part) for part in parts]
    tokens.append(date.strftime("%Y%m%d"))
    if ordinal is not None:
        tokens.append(str(ordinal))
    return "_".join(token for token in tokens if token) + (
        f".{extension.lstrip('.').lower()}"
    )


def build_filename_machine(
    machine_code: str,
    document_type_code: str,
    date: datetime.date,
    ordinal: int = None,
    extension: str = "pdf",
) -> str:
    """
    Build the fixed-format filename for a MACHINE-domain document.

    ---

    Construye el nombre de archivo de formato fijo para un documento
    de dominio MÁQUINA.
    """
    return _build_filename(
        [machine_code, document_type_code], date, ordinal, extension,
    )


def build_person_folder_name(
    first_surname: str,
    second_surname: str,
    given_name: str,
) -> str:
    """
    Build the canonical VIRTUAL FOLDER name for a `PersonIdentity`
    (H31, S99 -- new PERSONAL/ACTIVOS|INACTIVOS structure). Reuses the
    same `_sanitize_token` normalisation as the filename builders below
    (accents stripped, uppercase, non-alphanumeric collapsed to a
    single underscore) so a person's folder name and their document
    filenames are built from the exact same rule -- never two
    divergent normalisations of the same three fields. An empty
    `second_surname` is omitted, same convention as
    `build_filename_personal`.

    ---

    Construye el nombre de CARPETA VIRTUAL canónico de una
    `PersonIdentity` (H31, S99 -- nueva estructura
    PERSONAL/ACTIVOS|INACTIVOS). Reutiliza la misma normalización
    `_sanitize_token` que los constructores de nombre de archivo de
    abajo (acentos fuera, mayúsculas, todo lo que no sea alfanumérico
    colapsado a un único guion bajo) para que el nombre de carpeta de
    una persona y sus nombres de archivo salgan siempre de la misma
    regla -- nunca dos normalizaciones distintas de los mismos tres
    campos. Un `second_surname` vacío se omite, misma convención que
    `build_filename_personal`.
    """
    tokens = [
        _sanitize_token(part)
        for part in (first_surname, second_surname, given_name)
    ]
    return "_".join(token for token in tokens if token)


def build_company_folder_name(employer_company: str) -> str:
    """
    Build the canonical VIRTUAL FOLDER name for an employer company
    text (H31, S99 -- ACTIVOS subdivided by real employer, per Miguel
    Angel: "no hemos normalizado las empresas [...] la normalizacion
    de los nombres de empresa esta en el Excel"). Reuses the same
    `_sanitize_token` normalisation as every other folder/filename
    builder here -- deliberately does NOT merge known text variants of
    the same real company ("TRANSGRUAL SL" vs "TRANSGRUAL S.L.");
    Miguel Angel's own correction is to trust `PersonIdentity.
    employer_company` verbatim, refreshed straight from the Excel's
    own EMPRESA column per worker (`import_worker_machine_excel`),
    never a merge invented here.

    ---

    Construye el nombre de CARPETA VIRTUAL canónico para el texto de
    empresa empleadora (H31, S99 -- ACTIVOS subdividido por empresa
    real, según Miguel Ángel: "no hemos normalizado las empresas [...]
    la normalización de los nombres de empresa está en el Excel").
    Reutiliza la misma normalización `_sanitize_token` que el resto de
    constructores de carpeta/archivo de este módulo -- deliberadamente
    NO fusiona variantes de texto conocidas de la misma empresa real
    ("TRANSGRUAL SL" vs "TRANSGRUAL S.L."); la corrección explícita de
    Miguel Ángel es confiar en `PersonIdentity.employer_company` tal
    cual, refrescado directamente desde la columna EMPRESA del Excel
    por trabajador (`import_worker_machine_excel`), nunca una fusión
    inventada aquí.
    """
    return _sanitize_token(employer_company)


# ----------------------------------------------------------------------
# H31 (S99). Estructura real de carpetas virtuales de PERSONAL --
# ACTIVOS/{EMPRESA|GERENCIA|SIN_EMPRESA}, INACTIVOS, EPIS. Extraído a
# este módulo en S100 desde `restructure_personal_folders.py` (donde
# vivían como constantes/método de la Command) porque una segunda vía
# de escritura -- el alta de trabajador nuevo desde el panel (H31,
# S100) -- necesita la misma regla exacta de "en qué carpeta cae un
# PersonIdentity activo" sin duplicarla (principio DRY, doc-master
# sección 4.1.1). El comando de reorganización pasa a importar estas
# mismas constantes/función en vez de definirlas por su cuenta.
# ----------------------------------------------------------------------
PERSONAL_ROOT = "DOC. PERSONAL/PERSONAL"
ACTIVOS_ROOT = "%s/ACTIVOS" % PERSONAL_ROOT
INACTIVOS_ROOT = "%s/INACTIVOS" % PERSONAL_ROOT
EPIS_FOLDER = "%s/EPIS" % PERSONAL_ROOT

# Familia propietaria confirmada por Miguel Angel -- ACTIVOS/GERENCIA
# en vez de una carpeta de empresa, precisamente porque no son
# plantilla y por eso el Excel nunca les rellena employer_company.
# Match por apellidos exactos (normalizados), nunca por lista fija de
# DNI -- cualquier PersonIdentity futura con estos mismos dos
# apellidos entra en la misma regla.
GERENCIA_FOLDER_NAME = "GERENCIA"
GERENCIA_FIRST_SURNAME = "ALVAREZ"
GERENCIA_SECOND_SURNAME = "DIAZ"

# Fallback defensivo -- no debería ocurrir tras resolver los 5 de
# GERENCIA y refrescar employer_company desde el Excel real, pero la
# regla nunca debe fallar ni inventar una empresa si algún activo
# llega sin ninguna de las dos condiciones resuelta.
SIN_EMPRESA_FOLDER_NAME = "SIN_EMPRESA"


def build_person_category_root(
    first_surname: str,
    second_surname: str,
    employer_company: str,
    is_active_employee,
) -> str:
    """
    Resuelve la carpeta virtual raíz (sin el nombre de la persona
    todavía) donde debe vivir un `PersonIdentity` según la estructura
    ACTIVOS/{EMPRESA|GERENCIA|SIN_EMPRESA} o INACTIVOS (H31, S99).
    Misma regla exacta que usaba `restructure_personal_folders.
    Command._category_root_for`, ahora compartida desde aquí.
    """
    if not is_active_employee:
        return INACTIVOS_ROOT

    is_gerencia = (
        (first_surname or "").strip().upper() == GERENCIA_FIRST_SURNAME
        and (second_surname or "").strip().upper() == GERENCIA_SECOND_SURNAME
    )
    if is_gerencia:
        return "%s/%s" % (ACTIVOS_ROOT, GERENCIA_FOLDER_NAME)

    if employer_company:
        empresa_folder = build_company_folder_name(employer_company)
        return "%s/%s" % (ACTIVOS_ROOT, empresa_folder)

    return "%s/%s" % (ACTIVOS_ROOT, SIN_EMPRESA_FOLDER_NAME)


def build_filename_personal(
    first_surname: str,
    second_surname: str,
    given_name: str,
    document_type_code: str,
    date: datetime.date,
    ordinal: int = None,
    extension: str = "pdf",
) -> str:
    """
    Build the fixed-format filename for a PERSONAL-domain document.

    `first_surname`/`second_surname`/`given_name` must come from the
    person's own DNI content (resolved upstream, by the classification
    engine) -- never parsed back out of the source filename. An empty
    `second_surname` (rare, but not impossible) is simply omitted
    instead of leaving a stray double underscore.

    ---

    Construye el nombre de archivo de formato fijo para un documento
    de dominio PERSONAL.

    `first_surname`/`second_surname`/`given_name` deben venir del
    contenido real del DNI de la persona (resuelto aguas arriba, por
    el motor de clasificación) -- nunca extraídos de nuevo del nombre
    de archivo de origen. Un `second_surname` vacío (raro, pero
    posible) simplemente se omite en vez de dejar un doble guion bajo
    suelto.
    """
    return _build_filename(
        [first_surname, second_surname, given_name, document_type_code],
        date, ordinal, extension,
    )

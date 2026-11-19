# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/albaran_check.py
"""
Production delivery notes against clock-ins, compared by AI (S149).

---

Cotejo de albaranes de producción con los fichajes, por IA (H24, S149,
sesión invasora). Miguel Ángel: "desde la ficha de fichajes de un
trabajador, un botón para cargar una carpeta [...] los PDF son fotos,
hay que enviarlos a Gemini [...] comparamos con el fichaje del día y se
marcan las discrepancias para que el supervisor luego pueda visar o
modificar él lo que haya marcado la IA".

1. `stage_file`: cada PDF o foto de la carpeta se guarda en
   private/albaranes/<carga>/ (el supervisor lo vuelve a ver al visar).
2. `read_batch` (Celery): Gemini lee cada archivo (puede traer varios
   albaranes) y devuelve número, fecha, operario, máquina,
   observaciones y las cuatro horas del parte de producción.
3. `compare_day`: con los albaranes de un día monta la jornada que
   debería haber -- salida de base = entrada en desplazamiento, llegada
   al trabajo = trabajo efectivo, salida del trabajo = desplazamiento,
   llegada a base = salida -- conserva la pausa de comida fichada, y la
   cruza con los fichajes. Lo que se aparte más que los minutos de
   cortesía del horario del trabajador se corrige con el editor de
   jornada (`edit_presses`) como corrección por IA, a nombre de quien
   lanzó la carga; lo que no, se deja como se fichó. El día queda
   "Comparado por IA" (ClockDayAiCheck); el visado lo da después el
   supervisor (ClockDayReview).

Solo para quien ficha por tipos: los que no (taller, oficina) no
entregan estos albaranes (Miguel Ángel, S149).
"""
import datetime
import json
import logging
import os
import re
import secrets
import unicodedata

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

STAGING_DIR = os.path.join(settings.BASE_DIR, "private", "albaranes")
MAX_FILE_BYTES = 40 * 1024 * 1024
# S153 (Miguel Ángel: "hay que guardarlos en el cubo, estos albaranes no
# son como los de taller, aquellos son de terceros y estos son albaranes
# de trabajo. Van en carpetas diferentes"): cada archivo cargado se
# guarda también en el cubo principal, en la carpeta del trabajador,
# subcarpeta propia (los de taller van en "Fotos Albaranes").
ARCHIVE_BUCKET = "cgs_grupo_alvarez"
ARCHIVE_SUBFOLDER = "ALBARANES DE TRABAJO"
DEFAULT_TOLERANCE = 15
_MIME = {
    b"%PDF": "application/pdf",
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
}

_PROMPT = """
Eres un lector de partes de producción (albaranes) de una empresa de
grúas. El documento es una foto o un escaneo; puede traer uno o varios
albaranes (uno por página o varios en una página).

De cada albarán devuelve:
- number: el número de albarán impreso (p. ej. 348153).
- date: la fecha del servicio en formato AAAA-MM-DD (campo FECHA; el año
  puede venir con dos cifras).
- operator_name: el nombre escrito en "Nombre" del parte de producción.
- machine: el código de la máquina (p. ej. A-59).
- observations: el texto de Observaciones (p. ej. "hoja de ayudante").
- base_out: hora de "Salida base" (HH:MM, 24 h).
- base_in: hora de "Llegada base" (HH:MM).
- work_in: "Hora llegada trabajo" (HH:MM).
- work_out: "Hora salida trabajo" (HH:MM).
- vehicle_on_site: true si está marcada la casilla "Vehículo en obra"
  (arriba, junto al número de albarán); false si está vacía.
- continues_previous: true si está marcada la casilla "Continuación día
  ant." (junto a la anterior); false si está vacía.
- legible: false si no se pueden leer con seguridad la fecha o las horas.
- note: una frase corta si algo es dudoso (letra ilegible, hora
  tachada, dos horas posibles); vacío si todo está claro.

Las horas van en la tabla de arriba (columna "Hora"). No inventes nada:
un dato que no esté escrito va vacío. Si el documento no es un parte de
producción, devuelve la lista vacía.
"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "albaranes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "string"},
                    "date": {"type": "string"},
                    "operator_name": {"type": "string"},
                    "machine": {"type": "string"},
                    "observations": {"type": "string"},
                    "base_out": {"type": "string"},
                    "base_in": {"type": "string"},
                    "work_in": {"type": "string"},
                    "work_out": {"type": "string"},
                    "legible": {"type": "boolean"},
                    "note": {"type": "string"},
                    "vehicle_on_site": {"type": "boolean"},
                    "continues_previous": {"type": "boolean"},
                },
                "required": ["number", "date", "legible"],
            },
        },
    },
    "required": ["albaranes"],
}


class AlbaranError(Exception):
    """A problem the person can fix (file, folder or worker)."""


def _staged_abs(relative):
    path = os.path.normpath(os.path.join(STAGING_DIR, relative))
    if not path.startswith(os.path.normpath(STAGING_DIR) + os.sep):
        raise AlbaranError("Ruta de albarán no válida.")
    return path


def mime_of(data):
    """The file type of an uploaded albarán (PDF, JPEG or PNG), or ""."""
    for magic, mime in _MIME.items():
        if data.startswith(magic):
            return mime
    return ""


def stage_file(batch, filename, data):
    """
    Keep an uploaded albarán and create its sheet "Por leer".
    ---
    Guarda uno de los archivos de la carpeta y crea su albarán "Por
    leer" (la lectura lo reparte luego si trae varios).
    """
    from hr_calendar.models import AlbaranSheet

    if not data:
        raise AlbaranError("%s está vacío." % filename)
    if len(data) > MAX_FILE_BYTES:
        raise AlbaranError("%s pasa de 40 MB." % filename)
    mime = mime_of(data)
    if not mime:
        raise AlbaranError("%s no es un PDF ni una foto." % filename)
    extension = {"application/pdf": "pdf", "image/jpeg": "jpg",
                 "image/png": "png"}[mime]
    relative = os.path.join(str(batch.pk), "%s.%s" % (
        secrets.token_hex(12), extension))
    path = _staged_abs(relative)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    # S149: en la carga de varios no se sabe de quién es hasta leerlo;
    # se guarda en el cubo al repartirlo (read_batch).
    blob = (archive_in_bucket(batch, filename, data, mime, extension)
            if batch.person_id else "")
    return AlbaranSheet.objects.create(
        batch=batch, person=batch.person, original_name=filename[:255],
        staged_path=relative, bucket_blob=blob,
    )


def archive_in_bucket(batch, filename, data, mime, extension, person=None):
    """
    Keep a copy of an uploaded albarán in the worker's bucket folder.
    ---
    S153. Guarda el archivo tal cual en el cubo principal, en
    <carpeta del trabajador>/ALBARANES DE TRABAJO/, con la fecha y hora
    de la carga delante del nombre original (nunca sobrescribe), y lo
    deja en el índice del explorador. Sin carpeta del trabajador:
    ALBARANES DE TRABAJO/SIN CARPETA/<id del trabajador>/.
    """
    from document_explorer.index_writer import ensure_folder_chain
    from document_explorer.models import (
        DocumentIndexEntry,
        DocumentTypeCatalog,
        path_digest,
    )
    from spare_parts.gcs_service import upload_bytes

    person = person or batch.person
    base = (person.folder_path or "").strip("/")
    folder = ("%s/%s" % (base, ARCHIVE_SUBFOLDER) if base else
              "%s/SIN CARPETA/%s" % (ARCHIVE_SUBFOLDER, person.pk))
    stem = re.sub(r"[^0-9A-Za-z._-]+", "_", unicodedata.normalize(
        "NFKD", os.path.splitext(os.path.basename(filename))[0],
    ).encode("ascii", "ignore").decode()).strip("_")[:80] or "albaran"
    name = "%s_%s_%s.%s" % (
        timezone.localtime().strftime("%Y%m%d-%H%M%S"),
        secrets.token_hex(3), stem, extension)
    blob_name = "%s/%s" % (folder, name)
    try:
        ensure_folder_chain(ARCHIVE_BUCKET, folder)
        upload_bytes(ARCHIVE_BUCKET, blob_name, data, content_type=mime)
    except Exception as exc:  # noqa: BLE001 -- se informa al que carga
        logger.exception("Albarán sin guardar en el cubo: %s", blob_name)
        raise AlbaranError(
            "%s no se ha podido guardar en el cubo (%s)."
            % (filename, exc)) from exc
    DocumentIndexEntry.objects.create(
        bucket=ARCHIVE_BUCKET,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        blob_name=blob_name,
        blob_name_hash=path_digest(blob_name),
        parent_path=folder,
        parent_path_hash=path_digest(folder),
        name=name,
        size_bytes=len(data),
        content_type=mime,
        document_type=DocumentTypeCatalog.objects.filter(
            code="ALBARAN_TRABAJO").first(),
    )
    return blob_name


def staged_bytes(sheet):
    """The bytes of the file an albarán came in."""
    with open(_staged_abs(sheet.staged_path), "rb") as handle:
        return handle.read()


def _read_with_gemini(data, mime):
    from google.genai.types import GenerateContentConfig, HttpOptions, Part

    from ai_services.gemini_client import DEFAULT_MODEL, get_gemini_client
    from document_explorer.classification_service import (
        _generate_content_with_retry,
    )

    response = _generate_content_with_retry(
        get_gemini_client(),
        model=DEFAULT_MODEL,
        contents=[Part.from_bytes(data=data, mime_type=mime), _PROMPT],
        config=GenerateContentConfig(
            http_options=HttpOptions(timeout=180_000),
            response_mime_type="application/json",
            response_schema=_SCHEMA,
            temperature=0.0,
        ),
    )
    return json.loads(response.text.strip()).get("albaranes") or []


_TIME = re.compile(r"^\s*(\d{1,2})\s*[:.,h]\s*(\d{2})")


def parse_time(raw):
    """'7:30', '19.30', '8h00' -> time; anything else -> None."""
    match = _TIME.match(raw or "")
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return datetime.time(hour, minute)


def parse_day(raw):
    """'2026-11-12' (or with a two-digit year) -> date, else None."""
    match = re.match(r"^\s*(\d{2,4})-(\d{1,2})-(\d{1,2})", raw or "")
    if not match:
        return None
    year = int(match.group(1))
    year = year + 2000 if year < 100 else year
    try:
        return datetime.date(year, int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _plain(text):
    text = unicodedata.normalize("NFKD", text or "").encode(
        "ascii", "ignore").decode().upper()
    return set(re.findall(r"[A-Z]{3,}", text))


def _abbreviates(word, full):
    """
    Whether a written word is the name or a usual abbreviation of it.
    ---
    S149 (16/11, «Jose Garcia Fdez» es GARCÍA FERNÁNDEZ): la palabra
    escrita coincide con el nombre o el apellido completo, o es su
    abreviatura habitual: misma primera y última letra y el resto de sus
    letras en orden dentro del completo (Fdez → FERNANDEZ, Glez →
    GONZALEZ, Rguez → RODRIGUEZ, Hdez → HERNANDEZ).
    """
    if word == full:
        return True
    if len(word) < 3 or len(word) >= len(full) or (
            word[0] != full[0] or word[-1] != full[-1]):
        return False
    rest = iter(full[1:-1])
    return all(letter in rest for letter in word[1:-1])


def _hits(words, names):
    """The names (of a worker) that some written word matches."""
    return {name for name in names
            if any(_abbreviates(word, name) for word in words)}


def name_matches(person, written):
    """
    Whether the albarán name is plausibly the worker's.
    ---
    Si el nombre escrito en el albarán puede ser el del trabajador: al
    menos un apellido o el nombre coinciden (la letra es a mano y a
    veces solo viene el nombre y un apellido). Sin nombre escrito, se da
    por bueno.
    """
    words = _plain(written)
    if not words:
        return True
    own = _plain(" ".join(filter(None, (
        person.given_name, person.first_surname, person.second_surname))))
    return bool(_hits(words, own))


_SURNAME_WEIGHT = 2


def candidates(batch, marked=True):
    """
    Who the albaranes of a multi-worker batch can belong to.
    ---
    Carga de varios (S149): los trabajadores marcados en la lista al
    cargar o, sin marcados, todos los de la empresa que fichan por tipos
    (los únicos que entregan estos albaranes).
    """
    from document_explorer.models import PersonIdentity
    from hr_calendar.clock_settings import uses_types

    people = PersonIdentity.objects.filter(
        company=batch.company, company_user__isnull=False,
    ).select_related("company_user")
    if marked and batch.candidate_ids:
        people = people.filter(pk__in=batch.candidate_ids)
    today = timezone.localdate()
    return [p for p in people if uses_types(p.company_user, today)]


def match_batch_person(batch, people, written):
    """
    The worker of an albarán of a multi-worker batch, or None.
    ---
    S149 (19/11, carga del 18/11 con un solo trabajador marcado: sus 34
    albaranes quedaron «Sin trabajador»): primero entre los marcados y,
    si ninguno encaja, entre todos los que fichan por tipos.
    """
    person = match_person(people, written)
    if person is None and batch.candidate_ids:
        if not hasattr(batch, "_all_candidates"):
            batch._all_candidates = candidates(batch, marked=False)
        person = match_person(batch._all_candidates, written)
    return person


def match_person(people, written):
    """
    The worker whose name is written on the albarán, or None.
    ---
    El trabajador del nombre escrito (a mano) en el albarán: cada
    apellido que coincide (entero o abreviado, _abbreviates) suma 2 y
    cada palabra del nombre 1; vale el único que más suma, y siempre con
    algún apellido. Solo con el nombre de pila, o con un empate, no se
    adivina: queda "Sin trabajador" (S149: salvo que lo escrito sea el
    mote de uno solo, _by_nickname).
    """
    words = _plain(written)
    if not words:
        return None
    scored = []
    for person in people:
        surnames = _plain(" ".join(filter(None, (
            person.first_surname, person.second_surname))))
        given = _plain(person.given_name) - surnames
        surname_hits = len(_hits(words, surnames))
        # Sin ningún apellido no se adivina (solo el nombre de pila).
        if surname_hits:
            scored.append((_SURNAME_WEIGHT * surname_hits
                           + len(_hits(words, given)), person))
    scored.sort(key=lambda item: -item[0])
    if not scored or scored[0][0] < _SURNAME_WEIGHT or (
            len(scored) > 1 and scored[1][0] == scored[0][0]):
        return _by_nickname(people, words)
    return scored[0][1]


def _by_nickname(people, words):
    """
    The only worker whose nickname is the written name, or None.
    ---
    S149 (19/11, albaranes firmados «Leo»): sin apellido, vale el mote de
    la ficha si es exactamente lo escrito y solo lo tiene uno.
    """
    found = [p for p in people
             if (getattr(p, "nickname", "") or "").strip()
             and _plain(p.nickname) == words]
    return found[0] if len(found) == 1 else None


def read_batch(batch):
    """
    Read every albarán of a batch with Gemini, then compare each day.
    ---
    Lee con Gemini los archivos de la carga y compara cada día con los
    fichajes. Un archivo que trae varios albaranes se reparte en varias
    filas; uno que no se lee queda "Error" con su motivo.
    """
    from hr_calendar.models import AlbaranBatch, AlbaranSheet

    AlbaranBatch.objects.filter(pk=batch.pk).update(
        status=AlbaranBatch.Status.READING, heartbeat_at=timezone.now())
    people = None if batch.person_id else candidates(batch)
    for sheet in list(batch.sheets.filter(
            status=AlbaranSheet.Status.PENDING, position=1)):
        # S149: señal de vida antes de cada archivo (dos llamadas a
        # Gemini, como mucho unos minutos).
        AlbaranBatch.objects.filter(pk=batch.pk).update(
            heartbeat_at=timezone.now())
        try:
            data = staged_bytes(sheet)
            found = _read_with_gemini(data, mime_of(data))
        except Exception as exc:  # noqa: BLE001 -- se anota y se sigue
            logger.exception("# Albarán %s: no se ha podido leer", sheet.pk)
            sheet.status = AlbaranSheet.Status.ERROR
            sheet.note = ("No se ha podido leer: %s" % exc)[:255]
            sheet.save(update_fields=["status", "note"])
            continue
        if not found:
            sheet.status = AlbaranSheet.Status.UNREADABLE
            sheet.note = "No parece un parte de producción."
            sheet.save(update_fields=["status", "note"])
            continue
        made, archived = [], {}
        for position, item in enumerate(found, start=1):
            target = sheet if position == 1 else AlbaranSheet(
                batch=batch, original_name=sheet.original_name,
                staged_path=sheet.staged_path, position=position,
                bucket_blob=sheet.bucket_blob, person=sheet.person)
            # S149: carga de varios: el trabajador, por el nombre leído.
            if people is not None:
                target.person = match_batch_person(
                    batch, people, item.get("operator_name") or "")
            _fill(target, item, target.person)
            if target.person is None:
                target.status = AlbaranSheet.Status.NO_PERSON
                target.note = ("Nombre «%s»: no se sabe de qué trabajador "
                               "es (ninguno que fiche por tipos, o "
                               "varios posibles)." % (
                                   target.operator_name or "sin nombre",
                               ))[:255]
            elif not target.bucket_blob:
                # Al cubo, en la carpeta de su trabajador (una vez por
                # trabajador si el archivo trae albaranes de varios).
                if target.person_id not in archived:
                    try:
                        archived[target.person_id] = archive_in_bucket(
                            batch, sheet.original_name, data, mime_of(data),
                            os.path.splitext(sheet.staged_path)[1].lstrip(
                                ".") or "pdf", person=target.person)
                    except AlbaranError as exc:
                        archived[target.person_id] = ""
                        target.note = ("%s %s" % (target.note, exc)
                                       ).strip()[:255]
                target.bucket_blob = archived[target.person_id]
            target.save()
            made.append(target)
        # S153: la copia digital completa (todos los datos del albarán,
        # no solo las horas); si falla, el cotejo sigue y se repite con
        # backfill_albaranes_s153.
        try:
            from hr_calendar.albaran_full import store_full

            store_full(made, data, mime_of(data))
        except Exception:  # noqa: BLE001 -- se anota y se sigue
            logger.exception("# Albarán %s: sin copia completa", sheet.pk)
    if people is not None:
        rematch(batch, people)
    compare_batch(batch)


def rematch(batch, people=None):
    """
    Assign again the albaranes of a batch left "Sin trabajador".
    ---
    S149: vuelve a repartir, con lo que Gemini ya leyó (sin llamarle
    otra vez), los albaranes de una carga de varios que se quedaron sin
    trabajador (p. ej. tras mejorar el reparto por nombre). Los que ahora
    tienen dueño se guardan en su carpeta del cubo y pasan a leídos.
    Devuelve cuántos se han asignado.
    """
    from hr_calendar.models import AlbaranSheet

    if batch.person_id:
        return 0
    people = candidates(batch) if people is None else people
    done, archived = 0, {}
    for sheet in batch.sheets.filter(status=AlbaranSheet.Status.NO_PERSON):
        try:
            item = json.loads(sheet.raw or "{}")
        except ValueError:
            continue
        person = match_batch_person(batch, people,
                                    item.get("operator_name") or "")
        if person is None:
            continue
        sheet.person = person
        _fill(sheet, item, person)
        key = (sheet.staged_path, person.pk)
        if key not in archived:
            try:
                data = staged_bytes(sheet)
                archived[key] = archive_in_bucket(
                    batch, sheet.original_name, data, mime_of(data),
                    os.path.splitext(sheet.staged_path)[1].lstrip(".")
                    or "pdf", person=person)
            except (AlbaranError, OSError) as exc:
                archived[key] = ""
                sheet.note = ("%s %s" % (sheet.note, exc)).strip()[:255]
        sheet.bucket_blob = archived[key]
        sheet.save()
        done += 1
    return done


# S149 (17/11): Gemini leyó años y meses imposibles (2020, 2021, 2024,
# enero) y la IA creó días de fichaje enteros en esas fechas. Un
# albarán solo se coteja si su fecha cae entre DAY_WINDOW días antes de
# la carga y el día de la carga.
DAY_WINDOW = 62


def plausible_day(day, loaded_at):
    """
    Whether an albarán's date fits the day it was loaded.
    ---
    Si la fecha leída del albarán puede ser: no posterior al día de la
    carga ni de más de DAY_WINDOW días antes.
    """
    if day is None:
        return False
    loaded = timezone.localdate(loaded_at or timezone.now())
    return loaded - datetime.timedelta(days=DAY_WINDOW) <= day <= loaded


def fix_year(day, loaded_at):
    """
    The albarán's date with its year fixed, or None if it can't be.
    ---
    S149 (17/11, albarán 348065 de Mérida Alcaide leído como 16/11/2020,
    que era el 16/11/2026): si la fecha no cabe, prueba el mismo día y
    mes en el año de la carga y en el anterior; si uno cabe, es ese. Un
    día o un mes mal leídos no se adivinan (None: se revisa a mano).
    """
    if day is None or plausible_day(day, loaded_at):
        return None
    loaded = timezone.localdate(loaded_at or timezone.now())
    for year in (loaded.year, loaded.year - 1):
        try:
            candidate = day.replace(year=year)
        except ValueError:
            continue
        if plausible_day(candidate, loaded_at):
            return candidate
    return None


def _fill(sheet, item, person):
    from hr_calendar.models import AlbaranSheet

    sheet.raw = json.dumps(item, ensure_ascii=False)[:20000]
    sheet.number = (item.get("number") or "")[:40]
    sheet.day = parse_day(item.get("date"))
    loaded_at = getattr(sheet.batch, "created_at", None)
    fixed = fix_year(sheet.day, loaded_at)
    year_note = ""
    if fixed is not None:
        year_note = "Año corregido (leído %s)." % sheet.day.strftime(
            "%d/%m/%Y")
        sheet.day = fixed
    sheet.operator_name = (item.get("operator_name") or "")[:120]
    sheet.machine = (item.get("machine") or "")[:60]
    sheet.observations = (item.get("observations") or "")[:255]
    sheet.base_out = parse_time(item.get("base_out"))
    sheet.base_in = parse_time(item.get("base_in"))
    sheet.work_in = parse_time(item.get("work_in"))
    sheet.work_out = parse_time(item.get("work_out"))
    # S149 (17/11): casillas «Vehículo en obra» y «Continuación día ant.».
    sheet.vehicle_on_site = bool(item.get("vehicle_on_site"))
    sheet.continues_previous = bool(item.get("continues_previous"))
    sheet.name_mismatch = (person is not None
                           and not name_matches(person, sheet.operator_name))
    notes = [item.get("note") or "", year_note]
    has_times = any((sheet.base_out, sheet.base_in, sheet.work_in,
                     sheet.work_out))
    if sheet.day is None:
        notes.append("Sin fecha legible.")
    elif not plausible_day(sheet.day, getattr(sheet.batch, "created_at",
                                              None)):
        notes.append("Fecha dudosa (%s): revísala; no se coteja."
                     % sheet.day.strftime("%d/%m/%Y"))
    if not has_times:
        notes.append("Sin horas legibles.")
    legible = (item.get("legible", True) and has_times
               and plausible_day(sheet.day,
                                 getattr(sheet.batch, "created_at", None)))
    sheet.status = (AlbaranSheet.Status.READ if legible
                    else AlbaranSheet.Status.UNREADABLE)
    sheet.note = " ".join(n for n in notes if n)[:255]


STALL_MINUTES = 15
MAX_RESUMES = 3


def resume_stalled():
    """
    Resume the batches whose reading stopped half way.
    ---
    S149 (16/11): un reinicio de Celery (un despliegue) corta la lectura
    a medias y la carga se queda "Leyendo" para siempre. Las que llevan
    STALL_MINUTES sin señal se vuelven a mandar a leer: read_batch solo
    lee lo que sigue "Por leer", así que no se repite nada. Tras
    MAX_RESUMES reanudaciones (algo la tumba cada vez) no se insiste: lo
    que falta queda "Error" y se compara lo leído. Devuelve las cargas
    reanudadas.
    """
    from django.db.models import Q

    from hr_calendar.models import AlbaranBatch, AlbaranSheet
    from hr_calendar.tasks import read_albaran_batch_task

    limit = timezone.now() - datetime.timedelta(minutes=STALL_MINUTES)
    resumed = []
    for batch in AlbaranBatch.objects.filter(
            status=AlbaranBatch.Status.READING,
    ).filter(Q(heartbeat_at__lt=limit) | Q(heartbeat_at__isnull=True,
                                           created_at__lt=limit)):
        if batch.resumes >= MAX_RESUMES:
            batch.sheets.filter(status=AlbaranSheet.Status.PENDING).update(
                status=AlbaranSheet.Status.ERROR,
                note="Lectura interrumpida %d veces: no se ha leído."
                     % MAX_RESUMES)
            AlbaranBatch.objects.filter(pk=batch.pk).update(
                error="La lectura se cortó %d veces; lo que faltaba "
                      "queda sin leer." % MAX_RESUMES)
            compare_batch(batch)
            continue
        # Solo una reanudación a la vez (otro proceso puede verla igual).
        if AlbaranBatch.objects.filter(
                pk=batch.pk, heartbeat_at=batch.heartbeat_at,
                resumes=batch.resumes,
        ).update(heartbeat_at=timezone.now(), resumes=batch.resumes + 1):
            logger.warning("# Albaranes %s: lectura parada, se reanuda "
                           "(%d)", batch.pk, batch.resumes + 1)
            read_albaran_batch_task.delay(batch.pk)
            resumed.append(batch.pk)
    return resumed


def compare_batch(batch):
    """Compare every day of a batch and mark it ready."""
    from hr_calendar.models import AlbaranBatch, AlbaranSheet

    from document_explorer.models import PersonIdentity

    pairs = sorted(set(batch.sheets.filter(
        status=AlbaranSheet.Status.READ, day__isnull=False,
        person__isnull=False,
    ).values_list("person_id", "day")))
    people = PersonIdentity.objects.in_bulk({p for p, _day in pairs})
    for person_id, day in pairs:
        try:
            compare_day(batch, day, people[person_id])
        except Exception:  # noqa: BLE001 -- un día no para los demás
            logger.exception("# Albaranes %s: fallo al comparar %s (%s)",
                             batch.pk, day, person_id)
    AlbaranBatch.objects.filter(pk=batch.pk).update(
        status=AlbaranBatch.Status.READY, read_at=timezone.now())


def _types(company):
    from hr_calendar.models import ClockType

    active = list(ClockType.objects.filter(company=company, is_active=True))
    travel = next((t for t in active if t.role == ClockType.ROLE_TRAVEL),
                  None)
    meal = next((t for t in active if t.role == ClockType.ROLE_MEAL), None)
    work = (next((t for t in active if t.is_default and not t.role), None)
            or next((t for t in sorted(active, key=lambda t: t.order)
                     if t.counts_as_work and not t.role), None))
    return travel, work, meal


def tolerance_minutes(company_user):
    """The courtesy minutes of the worker's schedule (15 by default)."""
    from hr_calendar.clock_report import _schedule_times_by_user

    found = _schedule_times_by_user(company_user.company,
                                    [company_user.pk]).get(company_user.pk)
    minutes = found[3] if found else 0
    return int(minutes) if minutes else DEFAULT_TOLERANCE


def expected_presses(sheets, travel, work, start_by_car=False,
                     end_by_car=False):
    """
    The day as the albaranes tell it: [(kind, time, type or None)].
    ---
    La jornada según los albaranes del día, en orden: la salida de base
    del primero abre la jornada en desplazamiento; cada llegada al
    trabajo pasa a trabajo efectivo y cada salida del trabajo a
    desplazamiento (hacia el siguiente trabajo o de vuelta); la llegada a
    base del último la cierra. Si falta la salida de base, la jornada
    empieza al llegar al trabajo; si falta la llegada a base, acaba al
    salir del último trabajo.

    S149 (Miguel Ángel, 17/11: "si marca esa casilla, el camión se queda
    en la obra, el operario vuelve en coche [...] no se apunta nada; al
    día siguiente ese trabajador no tiene desplazamiento tampoco porque
    va en coche"): con `end_by_car` (el último albarán del día marca
    «Vehículo en obra») la jornada acaba al salir del trabajo, sin la
    vuelta; con `start_by_car` (el día anterior lo marcó, o el primer
    albarán dice «Continuación día ant.») empieza al llegar al trabajo,
    sin la ida.
    """
    ordered = sorted(sheets, key=lambda s: s.base_out or s.work_in
                     or s.work_out or s.base_in or datetime.time.max)
    points = []
    first, last = ordered[0], ordered[-1]
    if first.base_out and not start_by_car:
        points.append(("IN", first.base_out, travel.pk))
    for index, sheet in enumerate(ordered):
        if sheet.work_in:
            points.append(("CHG" if points else "IN", sheet.work_in,
                           work.pk))
        is_last = index == len(ordered) - 1
        if sheet.work_out and points:
            if is_last and (end_by_car or not last.base_in):
                points.append(("OUT", sheet.work_out, None))
            else:
                points.append(("CHG", sheet.work_out, travel.pk))
    if last.base_in and points and not (end_by_car and last.work_out):
        points.append(("OUT", last.base_in, None))
    points.sort(key=lambda p: p[1])
    return points


def day_locked(company_user, day):
    """
    Why the AI must not touch a day, or "" if it may.
    ---
    S149 (Miguel Ángel, 17/11): un día visado por un supervisor, o con
    alguna corrección manual (alguien lo revisó a mano), se queda como
    lo dejaron: ni el cotejo de una carga ni un comando lo cambian.
    """
    from django.db.models import Q

    from hr_calendar.models import ClockCorrection, ClockDayReview

    review = ClockDayReview.objects.filter(
        company_user=company_user, day=day,
    ).select_related("reviewed_by__user").first()
    if review is not None:
        who = getattr(getattr(review.reviewed_by, "user", None),
                      "get_full_name", lambda: "")() or "un supervisor"
        return "el día está visado por %s" % who
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(
        datetime.datetime.combine(day, datetime.time.min), tz)
    end = start + datetime.timedelta(days=1)
    # Las añadidas a mano no tienen fichaje corregido: van por la nueva.
    manual = ClockCorrection.objects.filter(
        Q(event__company_user=company_user, event__pressed_at__gte=start,
          event__pressed_at__lt=end)
        | Q(event__isnull=True, replacement__company_user=company_user,
            replacement__pressed_at__gte=start,
            replacement__pressed_at__lt=end),
        source__in=(ClockCorrection.Source.MANUAL,
                    ClockCorrection.Source.SYSTEM),
    ).select_related("corrected_by__user").order_by("-corrected_at").first()
    if manual is not None:
        who = getattr(getattr(manual.corrected_by, "user", None),
                      "get_full_name", lambda: "")() or "un supervisor"
        return "el día lo corrigió a mano %s" % who
    return ""


def compare_day(batch, day, person=None):
    """
    Compare one day with its albaranes; correct by AI what is off.
    ---
    Compara un día con sus albaranes. Corrige por IA lo que se aparte
    más que la cortesía del horario y deja el día "Comparado por IA" con
    el resumen. Devuelve el ClockDayAiCheck.
    """
    from hr_calendar.clock_corrections import (
        ClockCorrectionError, edit_presses,
    )
    from hr_calendar.models import (
        AlbaranSheet, ClockCorrection, ClockDayAiCheck, ClockEvent,
    )

    person = person or batch.person
    company_user = person.company_user
    # S149 (17/11): todos los albaranes leídos del día, de cualquier
    # carga (un albarán en otra carga dejaba el día cortado); el mismo
    # número cargado dos veces cuenta una, el de la carga más reciente.
    sheets, seen = [], set()
    for sheet in AlbaranSheet.objects.filter(
            batch__company=batch.company, day=day, person=person,
            status=AlbaranSheet.Status.READ,
    ).order_by("-batch__created_at", "position"):
        key = sheet.number or ("#%d" % sheet.pk)
        if key not in seen:
            seen.add(key)
            sheets.append(sheet)
    numbers = ", ".join(s.number or s.original_name for s in sheets)
    lines, car_notes = [], []
    travel, work, meal = _types(batch.company)
    corrected = False
    if company_user is None or travel is None or work is None:
        lines.append("No se puede comparar: el trabajador no tiene "
                     "usuario del panel o faltan los tipos de fichaje.")
    else:
        tolerance = tolerance_minutes(company_user)
        tz = timezone.get_current_timezone()

        def aware(t):
            return timezone.make_aware(datetime.datetime.combine(day, t), tz)

        start = aware(datetime.time.min)
        events = list(ClockEvent.objects.current().filter(
            company_user=company_user, pressed_at__gte=start,
            pressed_at__lt=start + datetime.timedelta(days=1),
        ).order_by("pressed_at"))
        # S149: sin desplazamiento de vuelta si el camión se queda en la
        # obra, ni de ida al día siguiente (va en coche).
        ordered = sorted(sheets, key=lambda s: s.base_out or s.work_in
                         or s.work_out or s.base_in or datetime.time.max)
        end_by_car = ordered[-1].vehicle_on_site
        start_by_car = (
            ordered[0].continues_previous
            or AlbaranSheet.objects.filter(
                person=person, day=day - datetime.timedelta(days=1),
                status=AlbaranSheet.Status.READ, vehicle_on_site=True,
            ).exists())
        if end_by_car:
            car_notes.append("Vehículo en obra: vuelve en coche, sin "
                             "desplazamiento de vuelta.")
        if start_by_car:
            car_notes.append("Va en coche a la obra (vehículo en obra "
                             "desde el día anterior): sin desplazamiento "
                             "de ida.")
        wanted = [(k, aware(t), ty) for k, t, ty in expected_presses(
            sheets, travel, work, start_by_car, end_by_car)]
        # La comida fichada se respeta si cae dentro de un tramo de
        # trabajo: su cambio a comida y la vuelta (al trabajo) siguen.
        work_spans = [(a[1], b[1]) for a, b in zip(wanted, wanted[1:])
                      if a[2] == work.pk]
        keep_meal = set()
        if meal is not None:
            for index, event in enumerate(events):
                if (event.kind == "CHG" and event.clock_type_id == meal.pk
                        and any(s <= event.pressed_at < e
                                for s, e in work_spans)):
                    wanted.append(("CHG", event.pressed_at, meal.pk))
                    keep_meal.add(event.pk)
                    back = events[index + 1] if index + 1 < len(events) \
                        else None
                    if back is not None and any(
                            s < back.pressed_at < e for s, e in work_spans):
                        wanted.append(("CHG", back.pressed_at, work.pk))
            wanted.sort(key=lambda w: w[1])
        rows, used = [], set()
        tolerance_delta = datetime.timedelta(minutes=tolerance)
        for kind, at, type_id in wanted:
            options = [e for e in events if e.pk not in used
                       and e.kind == kind]
            options.sort(key=lambda e: (
                (e.clock_type_id or None) != type_id,
                abs((e.pressed_at - at).total_seconds())))
            match = options[0] if options else None
            if match is None:
                rows.append({"id": None, "kind": kind, "at": at,
                             "type": type_id})
                lines.append("Añadido: %s a las %s." % (
                    _label(kind, type_id, travel, work, meal),
                    timezone.localtime(at).strftime("%H:%M")))
                continue
            used.add(match.pk)
            off = abs(match.pressed_at - at)
            same_type = (match.clock_type_id or None) == type_id
            if off <= tolerance_delta and same_type:
                rows.append({"id": match.pk, "kind": match.kind,
                             "at": match.pressed_at,
                             "type": match.clock_type_id})
                continue
            # Dentro de la cortesía se respeta la hora fichada y solo se
            # cambia el tipo.
            when = match.pressed_at if off <= tolerance_delta else at
            rows.append({"id": match.pk, "kind": kind, "at": when,
                         "type": type_id})
            lines.append("Corregido: %s de las %s a %s a las %s." % (
                _label(match.kind, match.clock_type_id, travel, work, meal),
                timezone.localtime(match.pressed_at).strftime("%H:%M"),
                _label(kind, type_id, travel, work, meal).lower(),
                timezone.localtime(when).strftime("%H:%M")))
        for event in events:
            if event.pk not in used:
                rows.append({"id": event.pk, "delete": True})
                lines.append("Anulado: %s de las %s (no está en el "
                             "albarán)." % (
                                 _label(event.kind, event.clock_type_id,
                                        travel, work, meal),
                                 timezone.localtime(
                                     event.pressed_at).strftime("%H:%M")))
        locked = day_locked(company_user, day)
        if locked and any(_changed(row, events) for row in rows):
            # S149 (Miguel Ángel, 17/11: "lo que esté ya visado lo dejamos
            # tal cual está"): la IA no toca un día visado ni uno que un
            # supervisor ha corregido a mano; deja dicho lo que vería.
            lines = ["No se corrige: %s. Lo que la IA cambiaría:" % locked] \
                + [line.replace("Corregido:", "cambiaría").replace(
                    "Añadido:", "añadiría").replace("Anulado:", "anularía")
                   for line in lines]
        elif any(_changed(row, events) for row in rows):
            reason = "Corrección por IA según albarán %s (tolerancia %d " \
                     "min)." % (numbers, tolerance)
            try:
                with transaction.atomic():
                    edit_presses(company_user, person, batch.created_by,
                                 reason, rows,
                                 source=ClockCorrection.Source.AI)
                corrected = True
            except ClockCorrectionError as exc:
                lines = ["No se ha podido corregir: %s" % exc] + lines
        if not lines:
            lines.append("Coincide con el albarán (dentro de %d min)."
                         % tolerance)
        lines = car_notes + lines
    if any(s.name_mismatch for s in sheets):
        lines.append("Aviso: el nombre del albarán (%s) no parece el del "
                     "trabajador." % ", ".join(
                         s.operator_name for s in sheets if s.name_mismatch))
    if company_user is None:
        return None
    check, _created = ClockDayAiCheck.objects.update_or_create(
        company_user=company_user, day=day,
        defaults={"batch": batch, "checked_by": batch.created_by,
                  "corrected": corrected, "albaranes": numbers[:255],
                  "summary": "\n".join(lines)},
    )
    return check


def _changed(row, events):
    if row.get("delete") or not row.get("id"):
        return True
    event = next((e for e in events if e.pk == row["id"]), None)
    if event is None or event.kind != row["kind"]:
        return True
    minute = row["at"].replace(second=0, microsecond=0)
    if event.pressed_at.replace(second=0, microsecond=0) != minute:
        return True
    # La salida no lleva tipo (edit_presses lo ignora).
    return row["kind"] != "OUT" and (
        (event.clock_type_id or None) != (row["type"] or None))


def _label(kind, type_id, travel, work, meal):
    if kind == "OUT":
        return "Salida"
    names = {getattr(t, "pk", None): t.name for t in (travel, work, meal)
             if t is not None}
    name = names.get(type_id, "otro tipo")
    return ("Entrada (%s)" % name) if kind == "IN" else name

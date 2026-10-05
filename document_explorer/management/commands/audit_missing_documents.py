# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/audit_missing_documents.py
"""
H30 (S127). Before saying a document is missing, read every file.

---

H30 (S127). Auditoría pedida por Miguel Ángel: antes de decir que a
una persona le falta un documento, se leen TODOS sus archivos
(`document_audit_service.candidate_files`) y Gemini dice de cada uno,
leyéndolo entero, si contiene ese documento de esa persona.

Por cada aviso de "Falta" de personal (DNI/NIE, permiso de conducción,
contrato) el informe dice:
- ENCONTRADO: qué archivo lo contiene, con qué tipo/fecha estaba en la
  BD (el porqué no contaba) y lo que Gemini ha leído (página, titular,
  número, fecha).
- FALTA CONFIRMADO: ninguno de los N archivos leídos lo contiene (y los
  que no se pudieron leer, aparte: mientras haya ilegibles no es
  "confirmado").

Verbosidad (com-standards 0bis, S127: la primera versión solo hacía
print() con redirección y Miguel Ángel pasó una tarde sin saber si hacía
algo): log propio con `--log-file`, pantalla y archivo a la vez con
flush en cada línea, una línea por archivo (leído / caché / copia
idéntica, y qué es), latido cada 20 archivos con avance y ETA con hora
de reloj.

SOLO LECTURA: no cambia nada en la BD. `--cache` guarda cada lectura
(archivo + documento buscado) para poder repetir o retomar sin volver a
pagar a Gemini. `--person` limita a una persona (pk).
"""
import json
import os
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from document_explorer import document_notice_service as notices
from document_explorer.employment_period_service import contract_covers
from document_explorer.document_audit_service import (
    candidate_files, content_key, find_in_file,
)
from document_explorer.models import PersonIdentity


def _wanted_for(notice):
    label = notice.document_label or ""
    if label in ("DNI", "DNI o NIE") or label.startswith("NIE"):
        return "IDENTIDAD"
    if label.startswith("Permiso de conducción"):
        return "PERMISO_CONDUCIR"
    if label.startswith("Contrato laboral"):
        return "CONTRATO"
    return None


def _in_own_record(entry, person):
    """
    True if the file is linked to the person or inside their folder.

    ---

    S127: "de otra persona" solo tiene sentido si el archivo está en la
    ficha de la auditada (vinculado o en su carpeta). Un archivo de otra
    persona con nombre parecido que entró en la búsqueda por su carpeta
    (Gutiérrez Nicolás Omar / Gutiérrez Santiago Nicolás) está en su
    sitio.
    """
    from django.contrib.contenttypes.models import ContentType

    if entry.domain_object_id == person.pk and (
        entry.domain_content_type_id
        == ContentType.objects.get_for_model(PersonIdentity).pk
    ):
        return True
    folder = (person.folder_path or "").rstrip("/")
    return bool(folder) and (
        entry.parent_path == folder
        or entry.parent_path.startswith(folder + "/")
    )


def _alta_dates(labels):
    """Alta dates named in 'Contrato laboral (alta del dd/mm/aaaa)'."""
    found = []
    for label in labels:
        match = re.search(r"alta del (\d{2}/\d{2}/\d{4})", label)
        if match:
            found.append(datetime.strptime(match.group(1), "%d/%m/%Y").date())
    return found


def _covers(result, altas):
    """For a contract: does the date read cover one of the altas?"""
    try:
        read = date.fromisoformat((result.get("key_date") or "")[:10])
    except ValueError:
        return "fecha no legible"
    hits = [alta for alta in altas if contract_covers(read, alta)]
    return (
        "CUBRE el alta del %s" % hits[0].strftime("%d/%m/%Y") if hits
        else "no cubre ninguna alta del aviso"
    )


class Command(BaseCommand):
    help = (
        "S127: lee todos los archivos de cada persona con un 'Falta' y "
        "dice si el documento está o falta de verdad. Solo lectura."
    )

    def add_arguments(self, parser):
        parser.add_argument("--cache", required=True)
        parser.add_argument("--log-file", required=True)
        parser.add_argument("--person", type=int)

    def _say(self, text):
        # Pantalla y archivo a la vez, con flush (com-standards 0bis).
        self.stdout.write(text)
        self.stdout.flush()
        self._log.write(text + "\n")
        self._log.flush()

    def _heartbeat(self, done, total):
        elapsed = time.monotonic() - self._started
        rate = elapsed / done if done else 0
        left = rate * (total - done)
        finish = datetime.now() + timedelta(seconds=left)
        self._say(
            "   ... avance %d/%d archivos (%d%%) -- quedan ~%d min, fin "
            "estimado a las %s" % (
                done, total, 100 * done // max(total, 1), left // 60,
                finish.strftime("%H:%M"),
            )
        )

    def handle(self, *args, **options):
        self._log = open(options["log_file"], "a", encoding="utf-8")
        self._started = time.monotonic()
        cache_path = options["cache"]
        cache = {}
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as handle:
                cache = json.load(handle)

        pending, _scheduled, _calendar = notices.compute_notices(
            notices.DOMAIN_PERSONAL,
        )
        wanted_by_person = defaultdict(dict)
        for notice in pending:
            if notice.kind != notices.KIND_MISSING:
                continue
            wanted = _wanted_for(notice)
            if wanted is None:
                continue
            person_pk = int(notice.notice_key.split("|")[1])
            if options["person"] and person_pk != options["person"]:
                continue
            wanted_by_person[person_pk].setdefault(wanted, []).append(
                notice.document_label,
            )
        people = PersonIdentity.objects.in_bulk(list(wanted_by_person))
        self._say("# [AUDITORÍA] Reuniendo los archivos de cada persona...")
        files_of = {
            pk: candidate_files(people[pk]) for pk in sorted(wanted_by_person)
        }
        total = sum(
            len(files_of[pk]) * len(wanted_by_person[pk])
            for pk in files_of
        )
        done = 0
        self._say("# [AUDITORÍA] %d lecturas posibles (archivo x documento "
                  "buscado); las de la caché y las copias idénticas no "
                  "llaman a Gemini." % total)
        self._say("# [AUDITORÍA] %d persona(s) con %d documento(s) "
                  "supuestamente ausentes." % (
                      len(people),
                      sum(len(w) for w in wanted_by_person.values())))
        totals = defaultdict(int)
        for person_pk in sorted(wanted_by_person):
            # Las lecturas de Gemini de una persona duran más que el
            # wait_timeout de MySQL en PythonAnywhere (EnterpriseBot_022:
            # "disconnected by the server because of inactivity"): se
            # reabre la conexión antes de cada consulta, como en el H28.
            close_old_connections()
            person = people[person_pk]
            files = files_of[person_pk]
            self._say("\n== pk=%s %s %s, %s -- %d archivo(s) candidatos" % (
                person.pk, person.first_surname, person.second_surname or "",
                person.given_name, len(files)))
            for wanted, labels in wanted_by_person[person_pk].items():
                found, unreadable, read = [], [], 0
                by_content = {}
                for position, entry in enumerate(files, 1):
                    key = "%s:%s" % (entry.pk, wanted)
                    result = cache.get(key)
                    same = content_key(entry)
                    source = "caché"
                    if (
                        (result is None or result.get("error"))
                        and same in by_content
                    ):
                        # Copia exacta (misma huella y tamaño) de un
                        # archivo ya leído en esta persona: mismo
                        # contenido, misma respuesta.
                        result = dict(by_content[same])
                        cache[key] = result
                        source = "copia idéntica"
                    # Un error guardado (timeout, formato) se reintenta:
                    # solo se reutiliza una lectura buena.
                    if result is not None and (
                        result.get("evidence") or ""
                    ).startswith("Número de documento"):
                        # Veredicto de la regla del número sin marcas de
                        # documento de identidad (S127): se rehace.
                        result = None
                    if result is None or result.get("error"):
                        source = "leído"
                        result = find_in_file(entry, person, wanted)
                        cache[key] = result
                        with open(cache_path, "w", encoding="utf-8") as out:
                            json.dump(cache, out, ensure_ascii=False)
                    if same and not result.get("error"):
                        by_content.setdefault(same, result)
                    done += 1
                    self._say("     [%s %d/%d] pk=%s %s (%s) -> %s" % (
                        wanted, position, len(files), entry.pk, entry.name,
                        source,
                        result.get("error") and "ERROR " + result["error"]
                        or ("SÍ ES" if result.get("found") else "no es")
                        + " -- " + (result.get("what") or "-")))
                    if done % 20 == 0:
                        self._heartbeat(done, total)
                    if result.get("error"):
                        unreadable.append((entry, result["error"]))
                        continue
                    read += 1
                    if result.get("found"):
                        found.append((entry, result))
                altas = _alta_dates(labels) if wanted == "CONTRATO" else []
                if altas:
                    # S127: un contrato de OTRO periodo no resuelve el
                    # aviso del alta actual (Ramírez, Triviño, Correa).
                    other_period = [
                        (entry, result) for entry, result in found
                        if not _covers(result, altas).startswith("CUBRE")
                    ]
                    found = [
                        pair for pair in found if pair not in other_period
                    ]
                    for entry, result in other_period:
                        self._say(
                            "     OTRO PERIODO pk=%s %s -> %s, fecha %s "
                            "(no cubre el alta del aviso)" % (
                                entry.pk, entry.name, result.get("what"),
                                result.get("key_date") or "-"))
                self._say("  -- %s (%s): %d leído(s), %d ilegible(s)" % (
                    wanted, "; ".join(labels), read, len(unreadable)))
                for entry, result in found:
                    if altas:
                        result = dict(result, evidence="%s [%s]" % (
                            result.get("evidence"), _covers(result, altas)))
                    self._say(
                        "     ENCONTRADO pk=%s [%s, %s%s] %s/%s\n"
                        "        lee: %s | págs %s | %s %s | fecha %s\n"
                        "        %s" % (
                            entry.pk,
                            entry.document_type.code
                            if entry.document_type else "sin tipo",
                            entry.issue_date or "sin fecha",
                            ", PAPELERA" if entry.deleted_at else "",
                            entry.parent_path, entry.name,
                            result.get("what"), result.get("pages"),
                            result.get("holder_name") or "",
                            result.get("holder_id") or "",
                            result.get("key_date") or "-",
                            result.get("evidence"),
                        )
                    )
                # Lo leído en CADA archivo, para que "falta confirmado" se
                # pueda comprobar a ojo (Miguel Ángel: nada por supuesto).
                for entry in files:
                    result = cache.get("%s:%s" % (entry.pk, wanted)) or {}
                    if result.get("error") or result.get("found"):
                        continue
                    if result.get("is_this_person") is False and (
                        _in_own_record(entry, person)
                    ):
                        self._say(
                            "     DE OTRA PERSONA pk=%s [%s] %s/%s -> %s "
                            "(titular: %s)" % (
                                entry.pk,
                                entry.document_type.code
                                if entry.document_type else "sin tipo",
                                entry.parent_path, entry.name,
                                result.get("what") or "-",
                                result.get("file_owner") or "?"))
                        totals["de_otra_persona"] += 1
                        continue
                    self._say("        leído pk=%s [%s] %s -> %s" % (
                        entry.pk,
                        entry.document_type.code
                        if entry.document_type else "sin tipo",
                        entry.name, result.get("what") or "-"))
                for entry, problem in unreadable:
                    self._say("     ILEGIBLE pk=%s %s/%s -- %s" % (
                        entry.pk, entry.parent_path, entry.name, problem))
                if found:
                    totals["encontrado"] += 1
                elif unreadable:
                    totals["sin_confirmar"] += 1
                    self._say("     SIN CONFIRMAR: no aparece en los "
                              "leídos, pero hay ilegibles.")
                else:
                    totals["falta_confirmado"] += 1
                    self._say("     FALTA CONFIRMADO: ninguno de los %d "
                              "archivo(s) lo contiene." % read)
        self._say("\n# [AUDITORÍA] Fin. Encontrados: %(encontrado)d. Falta "
                  "confirmado: %(falta_confirmado)d. Sin confirmar: "
                  "%(sin_confirmar)d. Archivos de otra persona: "
                  "%(de_otra_persona)d." % defaultdict(int, totals))

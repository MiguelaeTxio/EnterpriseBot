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

SOLO LECTURA: no cambia nada en la BD. `--cache` guarda cada lectura
(archivo + documento buscado) para poder repetir o retomar sin volver a
pagar a Gemini. `--person` limita a una persona (pk).
"""
import json
import os
import re
from collections import defaultdict
from datetime import date, datetime

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
        parser.add_argument("--person", type=int)

    def _say(self, text):
        self.stdout.write(text)
        self.stdout.flush()

    def handle(self, *args, **options):
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
            files = candidate_files(person)
            self._say("\n== pk=%s %s %s, %s -- %d archivo(s) candidatos" % (
                person.pk, person.first_surname, person.second_surname or "",
                person.given_name, len(files)))
            for wanted, labels in wanted_by_person[person_pk].items():
                found, unreadable, read = [], [], 0
                by_content = {}
                for entry in files:
                    key = "%s:%s" % (entry.pk, wanted)
                    result = cache.get(key)
                    same = content_key(entry)
                    if (
                        (result is None or result.get("error"))
                        and same in by_content
                    ):
                        # Copia exacta (misma huella y tamaño) de un
                        # archivo ya leído en esta persona: mismo
                        # contenido, misma respuesta.
                        result = dict(by_content[same])
                        cache[key] = result
                    # Un error guardado (timeout, formato) se reintenta:
                    # solo se reutiliza una lectura buena.
                    if result is None or result.get("error"):
                        result = find_in_file(entry, person, wanted)
                        cache[key] = result
                        with open(cache_path, "w", encoding="utf-8") as out:
                            json.dump(cache, out, ensure_ascii=False)
                    if same and not result.get("error"):
                        by_content.setdefault(same, result)
                    if result.get("error"):
                        unreadable.append((entry, result["error"]))
                        continue
                    read += 1
                    if result.get("found"):
                        found.append((entry, result))
                self._say("  -- %s (%s): %d leído(s), %d ilegible(s)" % (
                    wanted, "; ".join(labels), read, len(unreadable)))
                altas = _alta_dates(labels) if wanted == "CONTRATO" else []
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
                    if result.get("is_this_person") is False:
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

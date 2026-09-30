# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/reread_active_contracts.py
"""
H30 (S125). Rereads the contracts of ACTIVE workers only: dates, end
date of fixed-term contracts and employer company.

---

H30 (S125). Relee los contratos (contrato, prórroga, modificación) de
los trabajadores ACTIVOS -- solo ellos, nunca un inactivo, nunca se
activa a nadie (Miguel Ángel, S125) -- y deja en BD:

- la fecha de cada contrato y la de fin si es temporal (ningún contrato
  de los activos tenía fecha de fin: los temporales vencidos no se
  podían avisar);
- la empresa del contrato más reciente que la identifique (forma
  canónica del sistema), y su carpeta en ACTIVOS/{EMPRESA}/.

Una fecha existente nunca se borra por no poder leerla. Con --dry-run
no guarda nada: informa de lo que cambiaría. Salida en pantalla y en
archivo a la vez (--log-file), con progreso.

--shard N --shards M (S125): reparte los activos en M trozos (N desde
1) para lanzar M consolas en paralelo, cada una con su --log-file y su
--cache-file. Sin ellos, todos los activos en una sola ejecución.

--cache-file (S125): cada lectura de Gemini se guarda en un JSON en
cuanto se hace. La ejecución real reutiliza lo leído en la simulación
sin volver a llamar a Gemini (258 contratos, más de una hora), y si se
corta, al relanzarlo continúa donde iba.
"""
import json
import os
import time
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from document_explorer.contract_service import (
    apply_reading, dates_to_write, read_contract,
)
from document_explorer.employer_service import (
    canonical_employer_text, person_contracts,
)
from document_explorer.models import PersonIdentity
from document_explorer.person_folder_service import (
    expected_base_folder, free_folder_for, is_in_expected_folder,
    move_person_documents,
)


class Command(BaseCommand):
    """
    Reread active workers' contracts.

    ---

    Relee los contratos de los trabajadores activos.
    """

    help = (
        "Relee los contratos de los trabajadores ACTIVOS: fechas, fin de "
        "los temporales y empresa (nunca inactivos)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--log-file", default="")
        parser.add_argument("--cache-file", default="")
        parser.add_argument(
            "--shard", type=int, default=1,
            help="Trozo a procesar, desde 1.",
        )
        parser.add_argument(
            "--shards", type=int, default=1,
            help="Número total de trozos.",
        )

    def _log(self, message):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        self.stdout.write(line)
        if self._log_handle:
            self._log_handle.write(line + "\n")
            self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = (
            open(options["log_file"], "w", encoding="utf-8")
            if options["log_file"] else None
        )
        self._cache_path = options["cache_file"]
        self._cache = {}
        if self._cache_path and os.path.exists(self._cache_path):
            with open(self._cache_path, encoding="utf-8") as handle:
                self._cache = json.load(handle)
        self._shard, self._shards = options["shard"], options["shards"]
        if not 1 <= self._shard <= self._shards:
            raise CommandError(
                "--shard tiene que ir de 1 a %d." % self._shards,
            )
        try:
            self._run(options["dry_run"])
        finally:
            if self._log_handle:
                self._log_handle.close()

    def _run(self, dry_run):
        everyone = list(PersonIdentity.objects.filter(
            is_active_employee=True,
        ).order_by("first_surname", "second_surname", "given_name", "pk"))
        people = [
            person for index, person in enumerate(everyone)
            if index % self._shards == self._shard - 1
        ]
        self._log("Inicio%s: trozo %d de %d -- %d de %d trabajadores "
                  "ACTIVOS." % (
                      " (SIMULACIÓN, no se guarda nada)" if dry_run else "",
                      self._shard, self._shards, len(people), len(everyone),
                  ))
        totals = {
            "docs": 0, "dates": 0, "ends": 0, "errors": 0,
            "employer": 0, "moved": 0,
        }
        started = time.monotonic()
        for position, person in enumerate(people, start=1):
            self._person(position, person, dry_run, totals)
            elapsed = time.monotonic() - started
            eta = elapsed / position * (len(people) - position)
            if position % 5 == 0 or position == len(people):
                self._log("Progreso: %d/%d -- ETA %dm%02ds" % (
                    position, len(people), eta // 60, eta % 60,
                ))
        self._log(
            "Fin. Contratos leídos: %d (errores %d). Fechas cambiadas: "
            "%d, fechas de fin nuevas: %d. Empresas cambiadas: %d. "
            "Carpetas movidas: %d." % (
                totals["docs"], totals["errors"], totals["dates"],
                totals["ends"], totals["employer"], totals["moved"],
            )
        )

    def _reading(self, document):
        """
        Reading of one contract: from the cache, or Gemini (and cached).

        ---

        Lectura de un contrato: de la caché si ya se leyó, o de Gemini
        (y se guarda en la caché al momento).
        """
        from document_explorer.models import CompanyFiscalProfile
        from document_explorer.worker_request_service import _parse_iso

        # MySQL de PythonAnywhere cierra las conexiones inactivas y cada
        # lectura de Gemini deja la de este proceso parada: 2013 "Lost
        # connection" en los trozos 1 y 2 (S125). Se cierra y Django
        # abre una nueva al primer uso.
        connection.close()
        key = str(document.pk)
        if key in self._cache:
            cached = self._cache[key]
            if cached is None:
                return None
            return {
                "profile": CompanyFiscalProfile.objects.filter(
                    pk=cached["profile"],
                ).first() if cached["profile"] else None,
                "start_date": _parse_iso(cached["start_date"]),
                "end_date": _parse_iso(cached["end_date"]),
                "is_indefinite": cached["is_indefinite"],
            }
        reading = read_contract(document)
        self._cache[key] = None if reading is None else {
            "profile": reading["profile"].pk if reading["profile"] else None,
            "start_date": (
                reading["start_date"].isoformat()
                if reading["start_date"] else ""
            ),
            "end_date": (
                reading["end_date"].isoformat()
                if reading["end_date"] else ""
            ),
            "is_indefinite": reading["is_indefinite"],
        }
        if self._cache_path:
            with open(self._cache_path, "w", encoding="utf-8") as handle:
                json.dump(self._cache, handle)
        return reading

    def _person(self, position, person, dry_run, totals):
        name = "%s %s, %s (pk %s)" % (
            person.first_surname, person.second_surname,
            person.given_name, person.pk,
        )
        documents = list(person_contracts(person))
        if not documents:
            self._log("%d. %s: sin contratos." % (position, name))
            return
        self._log("%d. %s: %d contrato(s)." % (
            position, name, len(documents),
        ))
        readings = []
        for document in documents:
            totals["docs"] += 1
            try:
                reading = self._reading(document)
            except Exception as exc:  # noqa: BLE001 -- se registra
                totals["errors"] += 1
                self._log("   %s %s: ERROR de lectura: %s" % (
                    document.document_type.code, document.pk, exc,
                ))
                continue
            if reading is None:
                self._log("   %s %s: formato no legible." % (
                    document.document_type.code, document.pk,
                ))
                continue
            changes = dates_to_write(document, reading)
            if changes and not dry_run:
                apply_reading(document, reading)
            if changes:
                totals["dates"] += 1
                if changes.get("expiry_date"):
                    totals["ends"] += 1
            self._log("   %s %s: %s, inicio %s, fin %s%s%s" % (
                document.document_type.code, document.pk,
                reading["profile"].legal_name if reading["profile"]
                else "empresa no identificada",
                reading["start_date"] or "?",
                reading["end_date"] or (
                    "indefinido" if reading["is_indefinite"] else "-"
                ),
                " -- CAMBIA %s" % {
                    k: str(v) for k, v in changes.items()
                } if changes else "",
                "" if not changes or not dry_run else " (simulación)",
            ))
            readings.append((
                reading["start_date"] or document.issue_date, reading,
            ))
        connection.close()  # Tras las lecturas, conexión nueva (S125).
        dated = [item for item in readings if item[0] and item[1]["profile"]]
        if not dated:
            self._log("   Empresa: ningún contrato la identifica -- "
                      "se queda '%s'." % (person.employer_company or "vacía"))
            return
        dated.sort(key=lambda item: item[0], reverse=True)
        new = canonical_employer_text(dated[0][1]["profile"])
        if new != (person.employer_company or ""):
            totals["employer"] += 1
            self._log("   Empresa: '%s' -> '%s' (contrato del %s)." % (
                person.employer_company or "vacía", new, dated[0][0],
            ))
            person.employer_company = new
            if not dry_run:
                person.save(update_fields=["employer_company", "updated_at"])
        if not is_in_expected_folder(person):
            totals["moved"] += 1
            target = free_folder_for(person, expected_base_folder(person))
            origin = person.folder_path
            suffix = ""
            if not dry_run:
                with transaction.atomic():
                    moved = move_person_documents(person, target)
                suffix = " (%d archivo(s))" % moved
            self._log("   Carpeta '%s' -> '%s'%s." % (
                origin, target, suffix,
            ))

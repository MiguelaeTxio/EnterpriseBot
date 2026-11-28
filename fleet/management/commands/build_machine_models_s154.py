# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/management/commands/build_machine_models_s154.py
"""
S154 (invasora, 28/11) -- crea los modelos de máquina de los que se sabe
a ciencia cierta el modelo: agrupa los centros de gasto por su Marca /
Modelo y deja fuera los textos que no dicen el modelo (vacío, la marca
repetida como «MAN MAN», «SIN MODELO», acabados en «-»...).

Si un modelo tiene un solo manual (sin contar copias descartadas), lo
fija como el suyo. Si tiene varios, lo deja sin elegir y lo lista, para
decidir cuál se queda (extract_manual_counters_s154 --manual). No llama
a Gemini ni borra nada. Sin --apply solo lista lo que haría.
Escribe en pantalla y en su propio fichero de log a la vez
(com-standards 0bis).

---

S154 -- creates the machine models whose make/model is certain.
"""
import re
from collections import defaultdict
from datetime import datetime

from django.core.management.base import BaseCommand

from fleet.models import MachineAsset


def vague_reason(text):
    """
    Why a Marca / Modelo text does not say the model ("" if it does).

    ---

    Por qué un texto de Marca / Modelo no dice el modelo, o "" si sí.
    """
    upper = text.upper().strip()
    words = upper.rstrip("-").split()
    if not words:
        return "vacío"
    if "SIN MODELO" in upper or "SIN MARCA" in upper:
        return "sin modelo"
    if len(words) == 1:
        return "solo la marca (una palabra)"
    if words[0] == words[1] and not [
            w for w in words[2:] if w not in ("BENZ", "CUCHARA")]:
        return "la marca repetida, sin modelo"
    return ""


class Command(BaseCommand):
    """
    Creates the machine models whose make/model is certain.

    ---

    Crea los modelos de máquina con Marca / Modelo clara.
    """

    help = ("Crea los modelos de máquina de Marca / Modelo clara (sin "
            "--apply solo lista).")

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, text, stamp=True):
        line = ("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), text)
                if stamp else text)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        self._log_handle = open(options["log_file"], "a", encoding="utf-8")
        try:
            self._run(options)
        finally:
            self._log_handle.close()

    def _run(self, options):
        from fleet import manual_counters_service as service

        groups = defaultdict(list)
        for machine in MachineAsset.objects.order_by("code"):
            name = re.sub(r"\s+", " ", machine.brand_model or "").strip()
            groups[(machine.company_id, name.upper())].append(machine)
        clear, vague = [], []
        for (_company, _key), machines in sorted(
                groups.items(), key=lambda g: g[0][1]):
            name = re.sub(r"\s+", " ", machines[0].brand_model or "").strip()
            reason = vague_reason(name)
            (vague if reason else clear).append((name, machines, reason))
        self._log("Marca / Modelo claras: %s; sin modelo claro: %s."
                  % (len(clear), len(vague)))
        created = with_manual = several = without = 0
        pending = []
        for position, (name, machines, _r) in enumerate(clear, 1):
            manuals = service.machine_manuals(machines)
            codes = " ".join(m.code for m in machines)
            if options["apply"]:
                model = service.build_model(machines[0].company, name,
                                            machines)
                created += 1
                if len(manuals) == 1 and model.manual is None:
                    service.set_model_manual(model, manuals[0])
            if len(manuals) == 1:
                with_manual += 1
            elif manuals:
                several += 1
                pending.append((name, codes, manuals))
            else:
                without += 1
            self._log("[%s/%s] %s: %s -- %s manual(es)" % (
                position, len(clear), name, codes, len(manuals)))
        self._log("", stamp=False)
        self._log("RESUMEN", stamp=False)
        self._log("Modelos %s: %s" % (
            "creados o completados" if options["apply"] else "a crear",
            created if options["apply"] else len(clear)), stamp=False)
        self._log("   con un solo manual (queda fijado): %s" % with_manual,
                  stamp=False)
        self._log("   con varios manuales (hay que elegir): %s" % several,
                  stamp=False)
        self._log("   sin manual: %s" % without, stamp=False)
        self._log("", stamp=False)
        self._log("CON VARIOS MANUALES (elegir con --manual <id>):",
                  stamp=False)
        for name, codes, manuals in pending:
            self._log("%s (%s):" % (name, codes), stamp=False)
            for entry in manuals:
                self._log("   id %s: %s (%.1f MB)" % (
                    entry.pk, entry.name,
                    (entry.size_bytes or 0) / 1048576), stamp=False)
        self._log("", stamp=False)
        self._log("SIN MODELO CLARO (no se crean; hay que corregir su "
                  "Marca / Modelo):", stamp=False)
        for name, machines, reason in vague:
            self._log("«%s» (%s): %s" % (
                name, reason, " ".join(m.code for m in machines)),
                stamp=False)
        if not options["apply"]:
            self._log("Sin --apply: no se ha creado nada.", stamp=False)

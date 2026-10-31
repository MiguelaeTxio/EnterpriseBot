# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/management/commands/fix_assistance_cost_classes.py
"""
Fix the vehicle cost classes of the assistance services (H37, S142).

---

Deja bien las clases de vehículo de las medias de coste de la pestaña
Servicios, sin tener que marcar nada a mano (Miguel Ángel, S142:
"genera un comando de gestión que arregle todo este desbarajuste para no
estar yo marcando ahí y que me pueda volver a equivocar").

Para cada empresa con medias de coste:
1. Cada tipo de máquina de asistencia en una sola clase (el reparto de
   `DEFAULT_VEHICLE_COSTS`): vehículos de personal -> Furgoneta;
   asistencia en carretera y cabezas tractoras -> Remolcador/tractora;
   rescate y grúas móviles de 20 y 30 TM -> Grúa móvil; Turismo sin
   tipo. Crea la clase que falte.
2. Medias reales de los repostajes de GasoGes
   (`fleet_fuel_averages.apply_real_averages`): consumo por km o por
   hora de cada clase con al menos 10 tramos buenos y precio medio del
   gasoil; el consumo por hora de una clase con menos tramos se quita
   (vuelve a su consumo por km).
3. Recalcula coste y rendimiento de los servicios valorados (un
   presupuesto de 0 € de antes, tarifa sin precios, queda sin
   presupuesto).

Sin `--apply` lo hace todo dentro de una transacción y la deshace al
final: muestra lo que quedaría sin guardar nada. Log propio en
pantalla y en archivo a la vez (`--log-file`).
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from budgets.models import (
    DEFAULT_VEHICLE_COSTS,
    AssistanceCostSettings,
    AssistanceVehicleCost,
    ServiceEvaluation,
)


class Command(BaseCommand):
    """
    Fix the cost classes, apply the real averages and recompute.

    ---

    Arregla las clases de coste, aplica las medias reales y recalcula.
    """

    help = (
        "Deja cada tipo de máquina de asistencia en su clase de coste, "
        "aplica las medias reales de GasoGes y recalcula los servicios "
        "valorados (H37, S142). Sin --apply no guarda nada."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Guardar los cambios (sin esto, solo se muestran).",
        )
        parser.add_argument(
            "--log-file",
            required=True,
            help="Ruta del log propio (pantalla y archivo a la vez).",
        )

    def _log(self, message):
        """
        Print and append one line to the log file, flushed.

        ---

        Escribe una línea en pantalla y en el log, con flush.
        """
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message)
        print(line, flush=True)
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as handle:
            self._log_handle = handle
            self._run(options["apply"])

    def _run(self, apply):
        """
        Fix every company inside one transaction.

        ---

        Arregla cada empresa dentro de una transacción; sin --apply la
        deshace al final.
        """
        self._log("Inicio (%s)." % (
            "GUARDANDO" if apply else "SIMULACIÓN, no se guarda nada"
        ))
        with transaction.atomic():
            companies = [
                settings.company for settings in
                AssistanceCostSettings.objects.select_related("company")
            ]
            if not companies:
                self._log("No hay ninguna empresa con medias de coste.")
            for number, company in enumerate(companies, start=1):
                self._log("--- Empresa %d de %d: %s ---" % (
                    number, len(companies), company,
                ))
                self._fix_classes(company)
                self._apply_real(company)
                self._recompute(company)
            if not apply:
                transaction.set_rollback(True)
                self._log("Simulación: todo deshecho. Para guardar, "
                          "repetir con --apply.")
        self._log("Fin.")

    def _fix_classes(self, company):
        """
        One class per machine type, as in DEFAULT_VEHICLE_COSTS.

        ---

        Cada tipo de máquina en una sola clase, con el reparto de
        DEFAULT_VEHICLE_COSTS; crea la clase que falte.
        """
        from decimal import Decimal

        for order, (name, liters, types) in enumerate(
            DEFAULT_VEHICLE_COSTS, start=1,
        ):
            vehicle = AssistanceVehicleCost.objects.filter(
                company=company, name=name,
            ).first()
            if vehicle is None:
                vehicle = AssistanceVehicleCost.objects.create(
                    company=company, name=name,
                    fuel_liters_per_100km=Decimal(liters),
                    sort_order=order,
                )
                self._log("Clase creada: %s." % name)
            before = vehicle.type_names()
            wanted = [line for line in types.splitlines() if line.strip()]
            if before == wanted:
                self._log("%s: tipos ya correctos (%s)." % (
                    name, ", ".join(wanted) or "ninguno",
                ))
                continue
            vehicle.machine_types = "\n".join(wanted)
            vehicle.save(update_fields=["machine_types"])
            self._log("%s: tipos %s -> %s." % (
                name, ", ".join(before) or "ninguno",
                ", ".join(wanted) or "ninguno",
            ))
        others = AssistanceVehicleCost.objects.filter(
            company=company,
        ).exclude(name__in=[name for name, _l, _t in DEFAULT_VEHICLE_COSTS])
        for vehicle in others:
            if vehicle.machine_types:
                self._log("%s (clase propia): se le quitan los tipos %s, "
                          "que ya tienen su clase." % (
                              vehicle.name,
                              ", ".join(vehicle.type_names()),
                          ))
                vehicle.machine_types = ""
                vehicle.save(update_fields=["machine_types"])

    def _apply_real(self, company):
        """
        Apply the real GasoGes averages and log them per vehicle.

        ---

        Aplica las medias reales de GasoGes y las muestra por vehículo.
        """
        from budgets.fleet_fuel_averages import (
            MIN_CLASS_LEGS,
            apply_real_averages,
        )

        real, applied, skipped = apply_real_averages(
            company, clear_thin=True,
        )
        start, end = real["period"]
        if start:
            self._log("Repostajes del %s al %s." % (
                start.strftime("%d/%m/%Y"), end.strftime("%d/%m/%Y"),
            ))
        for vehicle in real["vehicles"]:
            if vehicle["unit"] == "h":
                measure = "%s h, %s l/h" % (vehicle["hours"],
                                            vehicle["l_hour"])
            else:
                measure = "%s km, %s l/100 km" % (vehicle["km"],
                                                  vehicle["l_100km"])
            self._log("  %s (%s) -> %s: %s, %d tramos, %d descartados." % (
                vehicle["code"], vehicle["type_name"],
                vehicle["class_name"] or "sin clase", measure,
                vehicle["legs"], vehicle["discarded"],
            ))
        self._log("Aplicado: %s." % (", ".join(applied) or "nada"))
        if skipped:
            self._log("No usado por tener menos de %d tramos buenos: "
                      "%s." % (MIN_CLASS_LEGS, ", ".join(skipped)))

    def _recompute(self, company):
        """
        Recompute the valued services and log the result.

        ---

        Recalcula los servicios valorados y muestra cómo quedan.
        """
        from budgets.service_evaluation import recompute_company

        recompute_company(company)
        evaluations = ServiceEvaluation.objects.filter(
            company=company, status=ServiceEvaluation.STATUS_DONE,
        ).order_by("pk")
        self._log("Servicios valorados recalculados: %d." % (
            evaluations.count(),
        ))
        for number, evaluation in enumerate(evaluations, start=1):
            self._log(
                "  %d. %s: presupuesto %s, coste %s, rendimiento %s." % (
                    number, evaluation.file_name,
                    evaluation.budget_amount, evaluation.total_cost,
                    evaluation.margin,
                ),
            )

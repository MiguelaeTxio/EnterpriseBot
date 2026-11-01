# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/management/commands/set_assistance_wear_costs.py
"""
Set the vehicle wear cost per km of the assistance classes (H37, S142).

---

Pone el coste del vehículo por km (desgaste: mantenimiento,
reparaciones y neumáticos, sin gasoil ni amortización) en las clases de
coste de la pestaña Servicios y recalcula los servicios valorados.

Fuente: Observatorio de Costes del Transporte de Mercancías por
Carretera, julio 2025 (Ministerio de Transportes), medias nacionales:
- Furgoneta (vehículo ligero, 50.000 km/año): 0,010840 + 0,019270 +
  703,70 / 50.000 = 0,044 €/km.
- Rígido de 2 ejes (90.000 km/año): 0,022582 + 0,030108 +
  3.322,25 / 90.000 = 0,0896 €/km.
- Rígido de 3 ejes (95.000 km/año): 0,025593 + 0,033119 +
  4.675,76 / 95.000 = 0,1079 €/km.

Decisión de Miguel Ángel (S142): Remolcador/tractora 0,100 €/km
(propuesta aceptada: mezcla plataformas, rígidos de 2 ejes, y cabezas
tractoras); Grúa móvil = rígido de 3 ejes más la diferencia entre el de
3 y el de 2 ejes: 0,1079 + (0,1079 - 0,0896) = 0,126 €/km.

Sin `--apply` lo hace dentro de una transacción y la deshace: muestra
lo que quedaría sin guardar nada. Log propio en pantalla y en archivo a
la vez (`--log-file`).
"""
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from budgets.models import (
    AssistanceCostSettings,
    AssistanceVehicleCost,
    ServiceEvaluation,
)

WEAR_COST_PER_KM = (
    ("Furgoneta", Decimal("0.044")),
    ("Remolcador/tractora", Decimal("0.100")),
    ("Grúa móvil", Decimal("0.126")),
)


class Command(BaseCommand):
    """
    Set the wear cost per km of each class and recompute.

    ---

    Pone el desgaste por km de cada clase y recalcula.
    """

    help = (
        "Pone el coste del vehículo por km (desgaste, Observatorio de "
        "costes 2025) en Furgoneta, Remolcador/tractora y Grúa móvil y "
        "recalcula los servicios valorados (H37, S142). Sin --apply no "
        "guarda nada."
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
        Set the costs of every company inside one transaction.

        ---

        Pone los costes de cada empresa en una transacción; sin --apply
        la deshace al final.
        """
        from budgets.service_evaluation import recompute_company

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
                for name, cost in WEAR_COST_PER_KM:
                    vehicle = AssistanceVehicleCost.objects.filter(
                        company=company, name=name,
                    ).first()
                    if vehicle is None:
                        self._log("%s: no existe la clase, se salta." % name)
                        continue
                    before = vehicle.cost_per_km
                    vehicle.cost_per_km = cost
                    vehicle.save(update_fields=["cost_per_km"])
                    self._log("%s: %s -> %s €/km." % (
                        name, before if before is not None else "vacío",
                        cost,
                    ))
                recompute_company(company)
                evaluations = ServiceEvaluation.objects.filter(
                    company=company, status=ServiceEvaluation.STATUS_DONE,
                ).order_by("pk")
                self._log("Servicios valorados recalculados: %d." % (
                    evaluations.count(),
                ))
                for row, evaluation in enumerate(evaluations, start=1):
                    self._log(
                        "  %d. %s: presupuesto %s, coste %s (vehículos "
                        "%s), rendimiento %s." % (
                            row, evaluation.file_name,
                            evaluation.budget_amount,
                            evaluation.total_cost,
                            evaluation.vehicles_cost, evaluation.margin,
                        ),
                    )
                    for note in evaluation.notes.splitlines():
                        if note.startswith(("Falta ", "«", "La tarifa")):
                            self._log("     aviso: %s" % note)
            if not apply:
                transaction.set_rollback(True)
                self._log("Simulación: todo deshecho. Para guardar, "
                          "repetir con --apply.")
        self._log("Fin.")

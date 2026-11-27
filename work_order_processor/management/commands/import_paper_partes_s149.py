# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/management/commands/import_paper_partes_s149.py
"""
Load the paper work orders of Plataformas (21-26/11/2026) as digital ones.

---

S149 (Miguel Ángel, 27/11: "Plataforma para empezar ya con el tema de
las partes de trabajo, al igual que hacen los del taller mecánico [...]
desde el día 20, como ya sabes, los periodos son del 21 al 20, para
tener desde el día 20 que esté ya cuadrado este mes, este periodo
entero"). PDF Partes_plataformas_27112026.pdf, 16 partes en papel de
José Antonio Zafra Balbuena, Nicolás Omar Gutiérrez y Rogerio Rodrigues
Regiani, transcritos a mano (PARTES, abajo).

Cada parte se carga como el parte digital que habría hecho el
trabajador desde su móvil (WorkOrder DIGITAL, cerrado y sin revisar, a
su nombre): un parte por trabajador y día (las dos hojas del mismo día
van juntas), pausa de comida de su horario descontada como en el
formulario, la lectura de HORAS como horómetro, los materiales de la
hoja de atrás como repuestos de la tarea de esa máquina. Sin máquina
escrita, «Taller» -> EMPRESA_TALLER_ELEVACION. Después compara cada día
con sus fichajes como hace el parte digital (hr_calendar/parte_clock.py),
salvo los días visados o corregidos a mano, que no se tocan.

Nunca carga un día que ya tenga parte digital de ese trabajador. Sin
--apply, simulación (deshace todo). Log propio (com-standards 0bis).
"""
import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

T = datetime.time

# (persona, fecha, [tareas], [materiales], notas)
# tarea: (máquina, desde, hasta, avería, reparación, horas de máquina)
# material: (referencia, máquina, material, unidades)
ZAFRA, NICOLAS, ROGERIO = 220, 228, 265
TALLER = "EMPRESA_TALLER_ELEVACION"
PARTES = [
    (ZAFRA, "2026-11-21", [
        (TALLER, "07:00", "12:00", "Revisar grupos electrógenos", "", None),
    ], [], "Sábado."),
    (ZAFRA, "2026-11-23", [
        ("Z124", "06:30", "11:00", "Ir avería Marbella (Dunique)", "", None),
        (TALLER, "11:00", "13:30", "Mover grupo y caseta pintura", "", None),
    ], [], ""),
    (ZAFRA, "2026-11-24", [
        ("Z124", "08:00", "13:30", "Localizar avería TILT", "", None),
        ("4216LYS", "15:00", "18:30", "Comenzar montar kit conversión",
         "Toma de fuerza", None),
    ], [], ""),
    (ZAFRA, "2026-11-25", [
        ("4216LYS", "08:00", "10:00", "Terminar montar kit conversión toma",
         "Fuerza", None),
        (TALLER, "10:30", "13:30", "Limpiar zona trabajo", "", None),
        ("Z14", "15:00", "18:30", "Sacar motor", "", None),
    ], [], ""),
    (ZAFRA, "2026-11-26", [
        ("Z14", "08:00", "10:00", "Sacar cárter y llevar a soldar", "", None),
        ("Z120", "10:30", "13:30", "Con Nico solucionar arranque", "",
         None),
        ("Z14", "15:00", "18:30", "Colocar cárter y montar motor", "Lavar",
         None),
    ], [], ""),
    (NICOLAS, "2026-11-21", [
        ("Z115", "07:30", "10:30", "Cambio de joystick de tracción",
         "Se completó con hidráulico. Comprobación. Lavado", 4250),
        (TALLER, "10:30", "12:00", "Movimiento de grupos en patio",
         "Puesto en carga de tijeras", None),
    ], [], "Sábado."),
    (NICOLAS, "2026-11-23", [
        ("T27", "08:00", "09:00", "No arrancaba. Sobre + perdido",
         "Comprobación", 2942),
        (TALLER, "09:00", "10:00",
         "Puesta en carga de tijeras. Reparación enchufe de Z32", "", None),
        ("Z14", "10:30", "12:00", "Traslado Málaga. Cárter roto",
         "Se posicionó para cargarla con grúa al camión", 3199),
        ("V07", "12:00", "13:30",
         "Se pidieron filtros aceite, aire y gasoil, se retiraron",
         "Para realizarle el servicio", None),
        ("Z120", "15:00", "18:30",
         "Se desmontaron las bombas porque estaban mal montadas",
         "Montaje de inyectores. Puesta en carga de batería", 3031),
    ], [], "Dos hojas del mismo día."),
    (NICOLAS, "2026-11-24", [
        (TALLER, "08:00", "09:00", "Movimiento de máquinas en patio", "",
         None),
        ("Z08", "09:00", "10:00", "Traslado P. Trevenez. Fallo en arranque",
         "Cambio de batería", 6851),
        ("Z17", "10:30", "11:30",
         "Se ayuda a Rogerio a desmontar suspensión",
         "Inferior de rueda derecha", None),
        ("T27", "11:30", "16:00",
         "Traslado Marbella. Limpieza de filtro aire",
         "Se apagaba por purgue abierto de bomba inyec.", 2943),
        ("Z120", "16:30", "18:30",
         "Se desmontaron todas las bombas inyectoras",
         "Montaron correctamente. Fallo en bolo no abre apertura de bombas",
         3031),
    ], [], "Dos hojas del mismo día. En la hoja: «+2 1c»."),
    (NICOLAS, "2026-11-25", [
        ("Z100", "08:00", "10:00", "Cambio de motor de arranque",
         "Cambio de batería. Comprobación", 450),
        ("Z69", "10:30", "13:30", "Montaje de mesas inyect. Puesta en marcha",
         "Calibración sensores peso. Repostaje", 6929),
        ("CAMION COSTA", "15:00", "16:00",
         "Cambio de tórica en cilindro bajada emergencia", "", None),
        ("Z79", "16:00", "18:30", "Fallo en movimiento de cesta",
         "Cambio de espadines y solenoides", 3272),
    ], [], ""),
    (NICOLAS, "2026-11-26", [
        ("T26", "08:00", "10:00", "Fallo en marchas", "", 596),
        ("Z120", "10:30", "13:30",
         "Se cambió solenoide de arranque y se trasladó a taller",
         "Inicio desmontar bombas de elev. y traslación", 3032),
        ("Z43", "15:00", "18:30",
         "Fallo en cesta, no giraba. Se realizó regulación de válvulas",
         "Modificación de parámetros con el ordenador", 1912),
    ], [], ""),
    (ROGERIO, "2026-11-23", [
        (TALLER, "08:00", "11:30",
         "Recoger canastilla en Málaga, llevar Estepona", "", None),
        ("V07", "11:30", "13:30", "Revisión",
         "Cambiar filtro aceite, gasoil, aire y aceite motor", None),
        ("Z17", "15:00", "18:30", "Cambiar disco de freno izquierdo",
         "Disco de freno cambiado", None),
    ], [
        ("37299-CLC", "V07", "Filtro gasoil", 1),
        ("C-21-630/4", "V07", "Filtro aire", 1),
        ("W 950/26", "V07", "Filtro aceite motor", 1),
    ], "En la hoja pone 23/01/2026: es el 23/11 (va entre el 21 y el 24)."),
    (ROGERIO, "2026-11-24", [
        ("Z17", "08:00", "17:30",
         "Cambio disco freno, bieleta, trapecio suspensión, revisión",
         "Cambio filtro aire, gasoil, aceite, aceite motor, trapecio "
         "suspensión, bieleta derecha izquierda", None),
        ("Z69", "17:30", "18:30", "Instalar turbo", "Instalado admisión",
         None),
    ], [
        ("5539400", "Z17", "Filtro gasoil", 1),
        ("H10W17", "Z17", "Filtro aceite motor", 1),
        ("E879L", "Z17", "Filtro aire", 1),
        ("GDB3439", "Z17", "Pastilla de freno", 4),
        ("55588", "Z17", "Disco de freno", 2),
        ("MI-LS-2776", "Z17", "Bieleta", 2),
    ], ""),
    (ROGERIO, "2026-11-25", [
        ("Z69", "08:00", "13:30", "Instalar turbo y inyectores",
         "Turbo instalado, inyectores, filtro aceite y aceite motor "
         "cambiado", None),
        ("Z14", "15:00", "17:30", "Quitado motor", "Motor quitado", 3199),
        ("Z79", "17:30", "18:30", "Cambiar válvula y bobina",
         "Cambiado los dos", 3272),
    ], [
        ("50434", "Z69", "Filtro aceite", 1),
        ("04286251", "Z69", "Inyector", 4),
        ("01148133", "Z69", "Torn. cabe. escap.", 2),
        ("04128865", "Z69", "Tubo retorno aceite", 1),
        ("02931741", "Z69", "Juego juntas completo", 1),
    ], ""),
    (ROGERIO, "2026-11-26", [
        ("2049KZK", "08:00", "12:00", "Cambiar pastilla freno",
         "Pastillas cambiadas", None),
        ("Z14", "12:00", "13:30", "Instalar motor",
         "Empezar instalación motor", 3200),
        ("Z120", "13:30", "16:30", "Quitar bomba hidráulica",
         "Quitando mangueras hidráulicas", 3032),
        ("Z14", "16:30", "18:30", "Instalar motor",
         "Motor instalado, cambio aceite, filtro aire, gasoil, aceite",
         3200),
    ], [
        ("GDB-2044", "2049KZK", "Pastilla freno delantero (2 pares)", 2),
        ("GDB-2410", "2049KZK", "Pastilla freno trasero (2 pares)", 2),
        ("C-1188", "Z14", "Filtro aire", 1),
        ("AVV-10X713", "Z14", "Correa motor", 1),
        ("FB10X950", "Z14", "Correa auxiliar", 1),
        ("814/80", "Z14", "Filtro aceite", 1),
        ("", "Z14", "Filtro gasoil", 1),
    ], ""),
]


class _Rollback(Exception):
    pass


def _t(text):
    hours, minutes = text.split(":")
    return T(int(hours), int(minutes))


def _minutes(value):
    return value.hour * 60 + value.minute


class Command(BaseCommand):
    help = ("Carga los partes en papel de Plataformas (21-26/11/2026) como "
            "partes digitales de cada trabajador.")

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--log-file", required=True)

    def _log(self, text):
        line = "[%s] %s" % (timezone.localtime().strftime("%H:%M:%S"), text)
        print(line, flush=True)
        self._out.write(line + "\n")
        self._out.flush()

    def handle(self, *args, **options):
        with open(options["log_file"], "a", encoding="utf-8") as out:
            self._out = out
            mode = ("APLICAR" if options["apply"]
                    else "SIMULACIÓN (no cambia nada)")
            self._log("MODO: %s" % mode)
            self._created = []
            try:
                with transaction.atomic():
                    self._run()
                    if not options["apply"]:
                        raise _Rollback()
            except _Rollback:
                self._log("Simulación: deshecho todo.")
                return
            self._after_commit()

    def _run(self):
        from document_explorer.models import PersonIdentity

        people = {p.pk: p for p in PersonIdentity.objects.filter(
            pk__in={row[0] for row in PARTES}).select_related(
            "company_user__user", "company_user__company")}
        total = Decimal("0")
        for person_id, day_text, tasks, parts, note in PARTES:
            person = people.get(person_id)
            if person is None or person.company_user_id is None:
                self._log("!! Persona %d sin usuario: no se carga el %s."
                          % (person_id, day_text))
                continue
            day = datetime.date.fromisoformat(day_text)
            hours = self._load(person, day, tasks, parts, note)
            total += hours or 0
        self._log("TOTAL de horas cargadas: %s" % total)
        self._correct_clock()

    def _lunch(self, company_user, day):
        """Ventana de comida de su horario ese día (13:30-15:00 si no)."""
        from panel.views_operator import _resolve_operator_schedule

        schedule = _resolve_operator_schedule(
            company_user, company_user.company)
        if schedule is not None and not schedule.is_intensive:
            on_day = schedule.for_day(day) if hasattr(
                schedule, "for_day") else schedule
            if (on_day is not None and on_day.end_time_morning
                    and on_day.start_time_afternoon):
                return on_day.end_time_morning, on_day.start_time_afternoon
        return T(13, 30), T(15, 0)

    def _asset(self, company, code):
        from fleet.models import MachineAsset

        clean = code.replace("-", "").replace(" ", "").upper()
        asset = MachineAsset.objects.filter(
            company=company, code__iexact=code).first()
        if asset is None:
            asset = MachineAsset.objects.filter(
                company=company, code__iexact=clean).first()
        if asset is None:
            for candidate in MachineAsset.objects.filter(
                    company=company).exclude(plate=""):
                if candidate.plate.replace("-", "").replace(
                        " ", "").upper() == clean:
                    return candidate
        return asset

    def _load(self, person, day, tasks, parts, note):
        from work_order_processor.models import (
            SparePartLine, WorkOrder, WorkOrderEntry, WorkOrderEntryLine,
        )

        company_user = person.company_user
        company = company_user.company
        label = "%s %s, %s · %s" % (
            person.first_surname, person.second_surname or "",
            person.given_name, day.strftime("%d/%m/%Y"))
        existing = WorkOrderEntry.objects.filter(
            work_order__uploaded_by=company_user,
            work_order__source=WorkOrder.Source.DIGITAL,
            work_date=day).values_list("work_order_id", flat=True).first()
        if existing:
            self._log("== %s: YA TIENE el parte digital nº %d: no se carga."
                      % (label, existing))
            return None
        lunch_start, lunch_end = self._lunch(company_user, day)
        worker_name = (company_user.user.get_full_name()
                       or company_user.user.username).upper()
        work_order = WorkOrder(
            company=company, uploaded_by=company_user,
            source=WorkOrder.Source.DIGITAL, status=WorkOrder.Status.DONE,
            total_pages=1, processed_pages=1, reviewed=False,
        )
        work_order.source_pdf.name = "%s_%s.pdf" % (
            worker_name, day.strftime("%d-%m-%Y"))
        work_order.save()
        entry = WorkOrderEntry.objects.create(
            work_order=work_order, page_number=1, worker_name=worker_name,
            work_date=day, uncertain_date=False,
            extraction_confidence=WorkOrderEntry.Confidence.HIGH,
            raw_gemini_response=None, lunch_break_start=lunch_start,
            lunch_break_end=lunch_end, no_lunch_break=False,
            has_diet=False, is_intensive_shift=False,
        )
        self._log("== %s -> parte nº %d (comida %s-%s)%s" % (
            label, work_order.pk, lunch_start.strftime("%H:%M"),
            lunch_end.strftime("%H:%M"), " · " + note if note else ""))
        lines_by_code = {}
        day_hours = Decimal("0")
        for number, (code, start, end, fault, repair, reading) in enumerate(
                tasks, 1):
            asset = self._asset(company, code)
            hc, hf = _t(start), _t(end)
            gross = _minutes(hf) - _minutes(hc)
            overlap = max(0, min(_minutes(hf), _minutes(lunch_end))
                          - max(_minutes(hc), _minutes(lunch_start)))
            hours = (Decimal(gross - overlap) / Decimal(60)).quantize(
                Decimal("0.01"))
            day_hours += hours
            line = WorkOrderEntryLine.objects.create(
                entry=entry, line_number=number, machine_asset=asset,
                machine_raw=asset.code if asset else code,
                machine_norm=asset.code if asset else code,
                fault_description=fault, repair_notes=repair,
                hc=hc, hf=hf, or_val="", delta_hours=hours, flags=[],
                engine_hours_reading=(
                    Decimal(reading) if reading is not None and asset
                    is not None and asset.has_engine_hours else None),
                is_on_site=False,
            )
            lines_by_code.setdefault(code, line)
            self._created.append(line.pk)
            self._log("   %d. %s %s-%s = %sh%s | %s%s%s" % (
                number, asset.code if asset else "%s (SIN FICHA)" % code,
                start, end, hours,
                " (comida descontada)" if overlap else "", fault,
                " | " + repair if repair else "",
                " | horas máquina %s" % reading if reading else ""))
        for number, (reference, code, material, quantity) in enumerate(
                parts, 1):
            line = lines_by_code.get(code) or next(iter(
                lines_by_code.values()))
            SparePartLine.objects.create(
                entry_line=line, line_number=number, reference=reference,
                vehicle=self._asset(company, code), material=material,
                quantity=Decimal(quantity), flags=[],
            )
            self._log("   repuesto: %s %s x%s (%s, tarea %d)" % (
                reference or "s/ref", material, quantity, code,
                line.line_number))
        self._log("   Horas del día: %s" % day_hours)
        self._days = getattr(self, "_days", [])
        self._days.append((company_user, day, work_order.pk))
        return day_hours

    def _correct_clock(self):
        from hr_calendar.albaran_check import day_locked
        from hr_calendar.parte_clock import correct_day

        self._log("--- Fichajes comparados con los partes ---")
        for company_user, day, number in getattr(self, "_days", []):
            who = "%s %s" % (company_user.user.username,
                             day.strftime("%d/%m"))
            if day_locked(company_user, day):
                self._log("   %s: visado o corregido a mano: no se toca."
                          % who)
                continue
            try:
                result = correct_day(company_user, day)
            except Exception as exc:  # que un día no pare los demás
                self._log("   %s: error: %s" % (who, exc))
                continue
            self._log("   %s: %s" % (who, getattr(result, "text", "")
                                     or getattr(result, "skipped", "")
                                     or "sin cambios"))

    def _after_commit(self):
        from work_order_processor.services import generate_work_order_excel
        from work_order_processor.tasks import classify_fault_line

        for company_user, day, number in getattr(self, "_days", []):
            try:
                generate_work_order_excel(number)
            except Exception as exc:
                self._log("   Excel del parte %d: %s" % (number, exc))
        for pk in self._created:
            try:
                classify_fault_line.apply_async(args=[pk], countdown=5)
            except Exception as exc:
                self._log("   Clasificar tarea %d: %s" % (pk, exc))
        self._log("Hecho: %d partes cargados." % len(
            getattr(self, "_days", [])))

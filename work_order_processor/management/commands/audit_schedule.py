from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Audita el horario activo y la pausa de comida del operario."

    def add_arguments(self, parser):
        parser.add_argument("entry_pk", type=int)

    def handle(self, *args, **options):
        from work_order_processor.models import WorkOrderEntry
        from ivr_config.models import WorkdaySchedule
        entry = WorkOrderEntry.objects.select_related("work_order").get(pk=options["entry_pk"])
        wo = entry.work_order
        company = wo.company
        self.stdout.write(f"WorkOrder pk={wo.pk} company={company} source={wo.source}")
        self.stdout.write(f"Entry pk={entry.pk} lb_start={entry.lunch_break_start} lb_end={entry.lunch_break_end} no_lunch={entry.no_lunch_break}")
        self.stdout.write(f"\nHorarios activos de la empresa:")
        for s in WorkdaySchedule.objects.filter(company=company):
            self.stdout.write(
                f"  pk={s.pk} label={s.label} "
                f"mañana={s.start_time_morning}-{s.end_time_morning} "
                f"tarde={s.start_time_afternoon}-{s.end_time_afternoon} "
                f"intensiva={s.is_intensive} default={s.is_default}"
            )

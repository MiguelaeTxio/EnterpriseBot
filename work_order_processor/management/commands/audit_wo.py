from django.core.management.base import BaseCommand
from work_order_processor.models import WorkOrder, WorkOrderEntry, WorkOrderEntryLine

class Command(BaseCommand):
    help = "Audita un WorkOrder concreto."

    def add_arguments(self, parser):
        parser.add_argument("pk", type=int)

    def handle(self, *args, **options):
        wo = WorkOrder.objects.get(pk=options["pk"])
        self.stdout.write(f"WO pk={wo.pk} source={wo.source} status={wo.status}")
        for e in wo.entries.all().prefetch_related("lines"):
            self.stdout.write(
                f"  Entry pk={e.pk} date={e.work_date} "
                f"lb_start={e.lunch_break_start} lb_end={e.lunch_break_end} "
                f"no_lunch={e.no_lunch_break} show_lunch={e.lunch_break_start is not None}"
            )
            for line in e.lines.all():
                self.stdout.write(
                    f"    Line pk={line.pk} hc={line.hc} hf={line.hf} "
                    f"delta={line.delta_hours}"
                )

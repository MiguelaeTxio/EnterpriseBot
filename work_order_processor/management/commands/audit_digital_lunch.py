from django.core.management.base import BaseCommand
from work_order_processor.models import WorkOrderEntry
from decimal import Decimal, ROUND_HALF_UP

def to_min(t):
    if not t: return None
    return t.hour * 60 + t.minute

def overlap(hc, hf, lb_s, lb_e):
    if not hc or not hf or not lb_s or not lb_e: return 0
    return max(0, min(to_min(hf), to_min(lb_e)) - max(to_min(hc), to_min(lb_s)))

class Command(BaseCommand):
    help = "Audita delta_hours de partes digitales contra pausa de comida."

    def handle(self, *args, **options):
        self.stdout.write(f"{'WO':<6} {'E':<6} {'L':<6} {'FECHA':<12} {'HC':<6} {'HF':<6} {'LB_S':<6} {'LB_E':<6} {'OLAP':<6} {'BRUTO':<7} {'NETO':<7} {'BD':<7} OK")
        self.stdout.write("-" * 100)
        entries = WorkOrderEntry.objects.filter(
            work_order__source__in=['DIGITAL','GENERATED'],
            work_order__status='DONE',
            no_lunch_break=False,
            lunch_break_start__isnull=False,
            lunch_break_end__isnull=False,
        ).select_related('work_order').prefetch_related('lines')
        for e in entries:
            for line in e.lines.all():
                if not line.hc or not line.hf or line.delta_hours is None:
                    continue
                gross_min = to_min(line.hf) - to_min(line.hc)
                gross = (Decimal(gross_min) / 60).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                olap = overlap(line.hc, line.hf, e.lunch_break_start, e.lunch_break_end)
                net = (Decimal(max(0, gross_min - olap)) / 60).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                ok = 'OK' if abs(float(line.delta_hours) - float(net)) < 0.01 else 'ERR'
                self.stdout.write(f"{e.work_order.pk:<6} {e.pk:<6} {line.pk:<6} {str(e.work_date):<12} {str(line.hc)[:5]:<6} {str(line.hf)[:5]:<6} {str(e.lunch_break_start)[:5]:<6} {str(e.lunch_break_end)[:5]:<6} {olap:<6} {float(gross):<7} {float(net):<7} {float(line.delta_hours):<7} {ok}")

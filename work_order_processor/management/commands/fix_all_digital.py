from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal, ROUND_HALF_UP
from work_order_processor.models import WorkOrder, WorkOrderEntry, WorkOrderEntryLine
from datetime import time

LUNCH_START = time(13, 30)
LUNCH_END   = time(15, 0)

def to_min(t):
    if not t: return None
    return t.hour * 60 + t.minute

def overlap(hc, hf):
    if not hc or not hf: return 0
    return max(0, min(to_min(hf), to_min(LUNCH_END)) - max(to_min(hc), to_min(LUNCH_START)))

def net_delta(hc, hf):
    gross = to_min(hf) - to_min(hc)
    net   = max(0, gross - overlap(hc, hf))
    return (Decimal(net) / 60).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

class Command(BaseCommand):
    help = "Audita y corrige delta_hours de TODOS los partes digitales."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', default=False)

    def handle(self, *args, **options):
        apply_mode = options['apply']
        self.stdout.write(f"# Modo: {'APLICAR' if apply_mode else 'DRY RUN'}")
        self.stdout.write(f"# Pausa: {LUNCH_START}-{LUNCH_END}")
        self.stdout.write("")

        wos = WorkOrder.objects.filter(
            source__in=['DIGITAL', 'GENERATED'],
            status='DONE',
        ).prefetch_related('entries__lines')

        total_err = 0
        fixes = []

        for wo in wos:
            for entry in wo.entries.all():
                for line in entry.lines.all():
                    if not line.hc or not line.hf or line.delta_hours is None:
                        continue
                    expected = net_delta(line.hc, line.hf)
                    stored   = line.delta_hours.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    olap     = overlap(line.hc, line.hf)
                    ok       = abs(float(expected) - float(stored)) < 0.01
                    if not ok:
                        total_err += 1
                        self.stdout.write(
                            f"ERR WO={wo.pk} E={entry.pk} L={line.pk} "
                            f"fecha={entry.work_date} hc={line.hc} hf={line.hf} "
                            f"olap={olap}min bd={stored} esperado={expected}"
                        )
                        fixes.append((line, entry, expected))

        self.stdout.write(f"\n# Total errores: {total_err}")

        if not apply_mode:
            self.stdout.write("# DRY RUN — ejecutar con --apply para corregir.")
            return

        self.stdout.write("# Aplicando correcciones...")
        with transaction.atomic():
            for line, entry, expected in fixes:
                line.delta_hours = expected
                line.save(update_fields=['delta_hours'])
                if not entry.lunch_break_start:
                    entry.lunch_break_start = LUNCH_START
                    entry.lunch_break_end   = LUNCH_END
                    entry.save(update_fields=['lunch_break_start', 'lunch_break_end'])

        self.stdout.write(f"# Corregidas {len(fixes)} líneas.")

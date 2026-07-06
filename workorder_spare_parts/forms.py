# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/workorder_spare_parts/forms.py
"""
Forms for the SparePartEntry catalog CRUD, outside the delivery-note
circuit (H10, condición sine qua non confirmada por Miguel Ángel el
2026-07-06 antes de avanzar con la integración en el parte de
trabajo).
---
Formularios para el CRUD del catálogo de SparePartEntry, fuera del
circuito de albaranes.
"""
from django import forms

from spare_parts.models import SparePartEntry


class SparePartEntryCatalogForm(forms.ModelForm):
    """
    Manual create/edit form for a SparePartEntry catalog record.

    Deliberately excludes fields owned by the delivery-note circuit
    (supplier_*, source_delivery_note_line) and the salvage circuit
    (origin_machine, origin_work_order_entry_line) -- those are
    populated automatically by their own flows (spare_parts.services
    and the H10 Paso 7 canibalización views), never edited here.

    ---

    Formulario de alta/edición manual de un registro del catálogo
    SparePartEntry. Excluye deliberadamente los campos propios del
    circuito de albaranes (supplier_*, source_delivery_note_line) y
    del circuito de canibalización (origin_machine,
    origin_work_order_entry_line) -- esos los rellenan
    automáticamente sus propios flujos, nunca se editan aquí.
    """

    class Meta:
        model = SparePartEntry
        fields = [
            'reference',
            'description',
            'is_uncountable',
            'stock_quantity',
            'stock_level',
            'status',
            'machine',
        ]
        widgets = {
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'is_uncountable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'stock_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'stock_level': forms.Select(
                attrs={'class': 'form-select'},
                choices=[
                    ('', '—'),
                    ('FULL', 'FULL'),
                    ('MEDIUM', 'MEDIUM'),
                    ('LOW', 'LOW'),
                    ('EMPTY', 'EMPTY'),
                ],
            ),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'machine': forms.Select(attrs={'class': 'form-select'}),
        }

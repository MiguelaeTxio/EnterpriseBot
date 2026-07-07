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
from django.urls import reverse_lazy

from spare_parts.models import SparePartEntry
from fleet.models import MachineAsset
from work_order_processor.models import WorkOrderEntryLine


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
            'internal_reference',
            'reference',
            'description',
            'is_uncountable',
            'stock_quantity',
            'stock_level',
            'status',
            'machine',
        ]
        widgets = {
            'internal_reference': forms.TextInput(attrs={
                'class': 'form-control', 'readonly': 'readonly',
            }),
            'reference': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Opcional -- referencia del proveedor actual, si la hay',
            }),
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


class SalvageEntryForm(forms.Form):
    """
    Alta manual de un repuesto recuperado por canibalización (H10
    Paso 7, anexo sección 3.6). No es un ModelForm porque combina
    campos de SparePartEntry con la elección de destino
    (WAREHOUSE / PRE_ASSIGNED + máquina receptora), que no es un
    campo del modelo -- resuelto en la vista/servicio
    (spare_parts.services.register_salvaged_entry), no aquí.

    Los querysets de origin_machine/origin_work_order_entry_line/
    destination_machine se acotan a la empresa en la vista (mismo
    patrón que SparePartEntryCatalogForm con `machine`).

    ---

    Manual creation of a spare part recovered via cannibalisation
    (H10 Paso 7, annex section 3.6). Not a ModelForm because it
    combines SparePartEntry fields with the destination choice
    (WAREHOUSE / PRE_ASSIGNED + receiving machine), which is not a
    model field -- resolved in the view/service
    (spare_parts.services.register_salvaged_entry), not here.

    origin_machine/origin_work_order_entry_line/destination_machine
    querysets are scoped to the company in the view (same pattern as
    SparePartEntryCatalogForm's `machine`).
    """

    DESTINATION_WAREHOUSE = SparePartEntry.STATUS_WAREHOUSE
    DESTINATION_PRE_ASSIGNED = SparePartEntry.STATUS_PRE_ASSIGNED
    DESTINATION_CHOICES = [
        (DESTINATION_WAREHOUSE, 'Almacén (rectificar/reutilizar más adelante)'),
        (DESTINATION_PRE_ASSIGNED, 'Directo a otra máquina/ticket'),
    ]

    description = forms.CharField(
        label='Descripción',
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: Bomba de agua recuperada de B14',
        }),
    )
    is_uncountable = forms.BooleanField(
        label='Es incontable',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    stock_quantity = forms.DecimalField(
        label='Cantidad',
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )
    stock_level = forms.ChoiceField(
        label='Nivel',
        required=False,
        choices=[('', '—'), ('FULL', 'FULL'), ('MEDIUM', 'MEDIUM'), ('LOW', 'LOW'), ('EMPTY', 'EMPTY')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    origin_machine = forms.ModelChoiceField(
        label='Máquina donante',
        queryset=MachineAsset.objects.none(),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'salvageOriginMachine',
            # Al cambiar de maquina donante, refresca tambien la
            # busqueda de partes recientes (mismo endpoint que el
            # input de texto libre) -- asi se ve la lista de partida
            # sin tener que escribir nada primero.
            'hx-get': reverse_lazy('workorder_spare_parts:salvage_origin_lines'),
            'hx-trigger': 'change',
            'hx-target': '#salvageOriginLineResults',
            'hx-swap': 'innerHTML',
            'hx-include': '#salvageOriginMachine, #salvageOriginLineSearch',
        }),
    )
    origin_work_order_entry_line = forms.ModelChoiceField(
        label='Parte de origen (opcional)',
        required=False,
        queryset=WorkOrderEntryLine.objects.none(),
        widget=forms.HiddenInput(attrs={'id': 'salvageOriginLine'}),
    )
    destination = forms.ChoiceField(
        label='Destino',
        choices=DESTINATION_CHOICES,
        initial=DESTINATION_WAREHOUSE,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'salvageDestination'}),
    )
    destination_machine = forms.ModelChoiceField(
        label='Máquina/ticket receptor',
        required=False,
        queryset=MachineAsset.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'salvageDestinationMachine'}),
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            machines = MachineAsset.objects.filter(
                company=company, is_active=True,
            ).order_by('code')
            self.fields['origin_machine'].queryset = machines
            self.fields['destination_machine'].queryset = machines
            # El queryset real de origin_work_order_entry_line se acota
            # a la máquina donante elegida vía la búsqueda HTMX
            # (SparePartSalvageOriginLinesView) -- aquí solo se valida
            # que, si llega un pk, pertenezca a la empresa.
            self.fields['origin_work_order_entry_line'].queryset = (
                WorkOrderEntryLine.objects.filter(
                    entry__work_order__company=company,
                )
            )

    def clean(self):
        cleaned = super().clean()
        is_uncountable = cleaned.get('is_uncountable')
        stock_quantity = cleaned.get('stock_quantity')
        stock_level = cleaned.get('stock_level')
        destination = cleaned.get('destination')
        destination_machine = cleaned.get('destination_machine')

        if is_uncountable:
            if not stock_level:
                self.add_error('stock_level', 'Obligatorio para un repuesto incontable.')
        else:
            if stock_quantity is None:
                self.add_error('stock_quantity', 'Obligatorio para un repuesto contable.')

        if destination == self.DESTINATION_PRE_ASSIGNED and not destination_machine:
            self.add_error(
                'destination_machine',
                'Obligatorio cuando el destino es directo a otra máquina/ticket.',
            )

        return cleaned

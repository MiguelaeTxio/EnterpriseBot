# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/spare_parts/forms.py
"""
Forms for the spare parts and supplier delivery note module.
---
Formularios del módulo de albaranes de proveedores y repuestos.
"""
from django import forms

from .models import Supplier


class SupplierForm(forms.ModelForm):
    """
    Create/edit form for a Supplier record.
    ---
    Formulario de alta/edición de un registro Supplier.
    """

    class Meta:
        model = Supplier
        fields = ['supplier_type', 'name', 'tax_id', 'address']
        widgets = {
            'supplier_type': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        """
        tax_id is required for EXTERNAL suppliers, must stay empty for
        SALVAGE (matches the model help_text and the unique constraint
        which only applies when tax_id is non-empty).
        ---
        tax_id es obligatorio para proveedores EXTERNAL, debe quedar
        vacío para SALVAGE (coherente con el help_text del modelo y la
        constraint de unicidad, que solo aplica cuando tax_id no está
        vacío).
        """
        cleaned = super().clean()
        supplier_type = cleaned.get('supplier_type')
        tax_id = cleaned.get('tax_id', '')
        if supplier_type == Supplier.TYPE_EXTERNAL and not tax_id:
            self.add_error('tax_id', 'Obligatorio para proveedores externos.')
        if supplier_type == Supplier.TYPE_SALVAGE and tax_id:
            self.add_error('tax_id', 'Debe quedar vacío para reciclado interno.')
        return cleaned

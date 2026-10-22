# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/forms_services.py
"""
H37 (S132). Form of the assistance work order data.

---

H37 (S132). Formulario de los datos de la orden de trabajo de
asistencia, el mismo para el alta (desde la foto de TIREA o a mano) y
para la edición. Los bloques siguen el albarán de TIREA y el apartado
9 del dossier de Pepe: servicio, cliente y vehículo asistido, recogida,
entrega y notas.
"""
from django import forms

from budgets.models import Insurer, VehicleType, WorkOrderAssistance

DATETIME_FORMAT = "%Y-%m-%dT%H:%M"

SERVICE_FIELDS = (
    "insurer", "vehicle_type", "service_date", "expediente",
    "provider_code", "policy_number", "client_name", "request_time",
    "service_start_time", "arrival_time", "load_time", "completion_time",
    "location_elapsed",
)
VEHICLE_FIELDS = (
    "insured_name", "client_phone", "vehicle_plate", "second_vehicle_plate",
    "vehicle_brand",
    "vehicle_model", "vehicle_color", "vehicle_type_label",
    "vehicle_subtype_label", "num_passengers", "breakdown_description",
    "breakdown_code", "vehicle_weight", "vehicle_height", "vehicle_length",
    "vehicle_axes", "vehicle_pma", "vehicle_tare",
)
PICKUP_FIELDS = (
    "pickup_type", "pickup_province", "vehicle_locality", "pickup_country",
    "pickup_cp", "pickup_location",
)
DELIVERY_FIELDS = (
    "delivery_type", "delivery_province", "delivery_locality",
    "delivery_country", "delivery_cp", "delivery_address", "driver_km",
    "total_km_tirea",
)
OTHER_FIELDS = (
    "is_failed", "is_billable", "is_accident", "insurer_comments",
    "company_observations", "extra_notes",
)


class WorkOrderAssistanceForm(forms.ModelForm):
    """
    Work order data, with the insurer and vehicle type of the company.

    ---

    Datos de la orden. Aseguradora y tipo de vehículo limitados a los de
    la empresa; el tipo de vehículo tiene que ser de la aseguradora
    elegida. El Motivo RIS va aparte (`ris_motive_text`): su lista de
    valores en el modelo sigue vacía a la espera de los valores reales
    del desplegable de TIREA, y con la lista vacía el modelo rechazaría
    cualquier valor.
    """

    ris_motive_text = forms.CharField(
        label="Motivo RIS",
        required=False,
        max_length=50,
    )

    class Meta:
        model = WorkOrderAssistance
        fields = (
            SERVICE_FIELDS + VEHICLE_FIELDS + PICKUP_FIELDS
            + DELIVERY_FIELDS + OTHER_FIELDS
        )
        labels = {
            "insured_name": "Conductor del vehículo asistido",
            "client_phone": "Teléfono del conductor",
            "vehicle_locality": "Localidad recogida",
            "pickup_location": "Dirección recogida",
            "insurer_comments": "Comentarios (TIREA)",
            "extra_notes": "Notas internas de oficina",
        }
        widgets = {
            "service_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d",
            ),
            "request_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format=DATETIME_FORMAT,
            ),
            "service_start_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format=DATETIME_FORMAT,
            ),
            "arrival_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format=DATETIME_FORMAT,
            ),
            "load_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format=DATETIME_FORMAT,
            ),
            "completion_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format=DATETIME_FORMAT,
            ),
            "insurer_comments": forms.Textarea(attrs={"rows": 3}),
            "company_observations": forms.Textarea(attrs={"rows": 2}),
            "extra_notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, company=None, **kwargs):
        """
        Limit the choices to the company and style the widgets.

        ---

        Limita las opciones a la empresa y da estilo a los campos.
        """
        super().__init__(*args, **kwargs)
        self.fields["insurer"].queryset = Insurer.objects.filter(
            company=company, is_active=True,
        ).order_by("name")
        self.fields["vehicle_type"].queryset = VehicleType.objects.filter(
            insurer__company=company, is_active=True,
        ).select_related("insurer").order_by("insurer__name", "sort_order")
        self.fields["vehicle_type"].label_from_instance = (
            lambda vehicle_type: (
                f"{vehicle_type.insurer.name} — {vehicle_type.name}"
            )
        )
        for name in ("request_time", "service_start_time", "arrival_time",
                     "load_time", "completion_time"):
            self.fields[name].input_formats = [DATETIME_FORMAT]
        if self.instance.pk and not self.is_bound:
            self.initial["ris_motive_text"] = self.instance.ris_motive or ""
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(widget, forms.Select):
                css = "form-select form-select-sm"
            else:
                css = "form-control form-control-sm"
            widget.attrs.setdefault("class", css)

    def clean(self):
        """
        The vehicle type must belong to the chosen insurer.

        ---

        El tipo de vehículo tiene que ser de la aseguradora elegida.
        """
        cleaned = super().clean()
        insurer = cleaned.get("insurer")
        vehicle_type = cleaned.get("vehicle_type")
        if insurer and vehicle_type and vehicle_type.insurer_id != insurer.pk:
            self.add_error(
                "vehicle_type",
                "Este tipo de vehículo es de otra aseguradora.",
            )
        return cleaned

    def save(self, commit=True):
        """
        Save, copying the RIS motive text to the model field.

        ---

        Guarda, pasando el Motivo RIS al campo del modelo.
        """
        self.instance.ris_motive = (
            self.cleaned_data.get("ris_motive_text") or None
        )
        return super().save(commit=commit)

    def blocks(self):
        """
        Bound fields grouped in the blocks of the TIREA albarán.

        ---

        Campos agrupados en los bloques del albarán de TIREA, para que
        la plantilla los pinte sin lógica propia.
        """
        groups = (
            ("Servicio", SERVICE_FIELDS),
            ("Vehículo asistido y conductor", VEHICLE_FIELDS),
            ("Recogida", PICKUP_FIELDS),
            ("Entrega", DELIVERY_FIELDS + ("ris_motive_text",)),
            ("Estado y notas", OTHER_FIELDS),
        )
        return [
            (title, [self[name] for name in names])
            for title, names in groups
        ]

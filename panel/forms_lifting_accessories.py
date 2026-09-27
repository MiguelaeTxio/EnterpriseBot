# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/forms_lifting_accessories.py
"""
H30 (S121). Forms of the "Accesorios de elevación" tab of the
Documentation hub: accessory, delivery, review and accessory type.

---

H30 (S121). Formularios de la pestaña "Accesorios de elevación" del hub
de Documentación: accesorio, entrega, revisión y tipo de accesorio.
"""

from django import forms

from document_explorer import lifting_accessory_service as service
from document_explorer.models import (
    DocumentIndexEntry,
    LiftingAccessory,
    LiftingAccessoryType,
    PersonIdentity,
)
from fleet.models import MachineAsset

_DATE_WIDGET = forms.DateInput(
    format="%Y-%m-%d",
    attrs={"type": "date", "class": "form-control form-control-sm"},
)


def _small(widget_class, **attrs):
    """
    Bootstrap small widget of the given class.
    ---
    Widget de Bootstrap en tamaño pequeño de la clase indicada.
    """
    css = (
        "form-select form-select-sm"
        if widget_class is forms.Select
        else "form-control form-control-sm"
    )
    return widget_class(attrs={"class": css, **attrs})


class PersonChoiceField(forms.ModelChoiceField):
    """
    Worker selector labelled "Surnames, Name" (never the ID number).
    ---
    Selector de trabajador con etiqueta "Apellidos, Nombre" (nunca el
    DNI, que sí sale en `PersonIdentity.__str__`).
    """

    def label_from_instance(self, obj):
        surnames = " ".join(
            part for part in (obj.first_surname, obj.second_surname) if part
        )
        return "%s, %s" % (surnames, obj.given_name)


class MachineChoiceField(forms.ModelChoiceField):
    """
    Machine selector labelled "code -- brand/model".
    ---
    Selector de máquina con etiqueta "código -- marca/modelo".
    """

    def label_from_instance(self, obj):
        if obj.brand_model:
            return "%s -- %s" % (obj.code, obj.brand_model)
        return obj.code


class DocumentChoiceField(forms.ModelChoiceField):
    """
    Document selector labelled "folder / file name".
    ---
    Selector de documento con etiqueta "carpeta / nombre de archivo".
    """

    def label_from_instance(self, obj):
        folder = obj.parent_path.rstrip("/")
        return "%s / %s" % (folder, obj.name) if folder else obj.name


def _responsible_field(required):
    """
    Active workers, by surname.
    ---
    Trabajadores activos, por apellidos.
    """
    return PersonChoiceField(
        queryset=PersonIdentity.objects.filter(
            is_active_employee=True,
        ).order_by("first_surname", "second_surname", "given_name"),
        required=required,
        label="Responsable",
        empty_label="-- Elegir trabajador --",
        widget=_small(forms.Select),
    )


def _machine_field(company):
    """
    Active machines of the company, by code.
    ---
    Máquinas activas de la empresa, por código.
    """
    return MachineChoiceField(
        queryset=MachineAsset.objects.filter(
            company=company, is_active=True,
        ).order_by("code"),
        required=False,
        label="Máquina",
        empty_label="-- Sin máquina --",
        widget=_small(forms.Select),
    )


class LiftingAccessoryForm(forms.ModelForm):
    """
    Create or edit one accessory. On create, an optional first delivery
    (responsible, machine, date) can be recorded in the same step.
    ---
    Alta o edición de un accesorio. En el alta se puede registrar en el
    mismo paso una primera entrega opcional (responsable, máquina,
    fecha).
    """

    class Meta:
        model = LiftingAccessory
        fields = [
            "accessory_type", "identifier", "description", "dimensions",
            "working_load_kg", "standard", "manufacturer", "supply_date",
        ]
        widgets = {
            "accessory_type": _small(forms.Select),
            "identifier": _small(forms.TextInput),
            "description": _small(forms.TextInput),
            "dimensions": _small(forms.TextInput),
            "working_load_kg": _small(forms.NumberInput, min="0"),
            "standard": _small(forms.TextInput),
            "manufacturer": _small(forms.TextInput),
            "supply_date": _DATE_WIDGET,
        }

    def __init__(self, *args, company=None, with_delivery=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["accessory_type"].queryset = (
            LiftingAccessoryType.objects.filter(is_active=True)
            | LiftingAccessoryType.objects.filter(
                pk=self.instance.accessory_type_id,
            )
        ).distinct()
        self.fields["accessory_type"].empty_label = "-- Elegir tipo --"
        self.with_delivery = with_delivery
        if with_delivery:
            # Solo en el alta: el certificado se vincula (uno existente,
            # ya tipado) o se sube (queda tipado al subirlo). En la ficha
            # tienen su propia sección, con varios por accesorio.
            self.fields["certificate_existing"] = DocumentChoiceField(
                queryset=service.certificate_candidates(),
                required=False,
                label="Certificado del fabricante (existente)",
                empty_label="-- Ninguno --",
                widget=_small(forms.Select),
            )
            self.fields["certificate_file"] = forms.FileField(
                required=False,
                label="o subir el certificado (PDF o imagen)",
                widget=forms.ClearableFileInput(attrs={
                    "class": "form-control form-control-sm",
                    "accept": ".pdf,.jpg,.jpeg,.png",
                }),
            )
            self.fields["responsible_person"] = _responsible_field(False)
            self.fields["machine"] = _machine_field(company)
            self.fields["start_date"] = forms.DateField(
                required=False, label="Fecha de entrega",
                widget=_DATE_WIDGET,
            )

    def clean(self):
        """
        Unique (company, type, identifier), and a complete first delivery.
        ---
        Único por (empresa, tipo, nº) -- la restricción de BD incluye la
        empresa, que no es campo del formulario, así que se comprueba
        aquí para dar un error legible en vez de un IntegrityError. Y
        la primera entrega, si se rellena, necesita responsable y fecha.
        """
        cleaned = super().clean()
        accessory_type = cleaned.get("accessory_type")
        identifier = (cleaned.get("identifier") or "").strip()
        cleaned["identifier"] = identifier
        if accessory_type and identifier and self.company is not None:
            clash = LiftingAccessory.objects.filter(
                company=self.company,
                accessory_type=accessory_type,
                identifier__iexact=identifier,
            ).exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error(
                    "identifier",
                    "Ya existe un accesorio de este tipo con ese nº.",
                )
        if self.with_delivery:
            person = cleaned.get("responsible_person")
            machine = cleaned.get("machine")
            start = cleaned.get("start_date")
            if (machine or start) and not person:
                self.add_error(
                    "responsible_person",
                    "Una entrega necesita siempre un responsable.",
                )
            if person and not start:
                self.add_error("start_date", "Indica la fecha de entrega.")
            if (cleaned.get("certificate_existing")
                    and cleaned.get("certificate_file")):
                self.add_error(
                    "certificate_file",
                    "Elige un certificado existente o sube uno, no ambos.",
                )
            upload = cleaned.get("certificate_file")
            if upload and not _is_certificate_file(upload.name):
                self.add_error(
                    "certificate_file",
                    "El certificado debe ser un PDF o una imagen.",
                )
        return cleaned


def _is_certificate_file(name):
    """
    Whether a file name has an accepted certificate extension.
    ---
    Si el nombre de archivo tiene una extensión admitida de certificado.
    """
    return name.rsplit(".", 1)[-1].lower() in ("pdf", "jpg", "jpeg", "png")


class LiftingAccessoryCertificateForm(forms.Form):
    """
    Link an existing certificate or upload a new one (exactly one).
    ---
    Vincular un certificado existente o subir uno nuevo (exactamente
    uno de los dos).
    """

    certificate_existing = DocumentChoiceField(
        queryset=DocumentIndexEntry.objects.none(),
        required=False,
        label="Vincular un certificado existente",
        empty_label="-- Ninguno --",
        widget=_small(forms.Select),
    )
    certificate_file = forms.FileField(
        required=False,
        label="o subir uno nuevo (PDF o imagen)",
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control form-control-sm",
            "accept": ".pdf,.jpg,.jpeg,.png",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["certificate_existing"].queryset = (
            service.certificate_candidates()
        )

    def clean(self):
        """
        Exactly one of the two, and only PDF or image uploads.
        ---
        Exactamente uno de los dos, y solo PDF o imagen al subir.
        """
        cleaned = super().clean()
        existing = cleaned.get("certificate_existing")
        upload = cleaned.get("certificate_file")
        if existing and upload:
            raise forms.ValidationError(
                "Elige un certificado existente o sube uno, no ambos.",
            )
        if not existing and not upload and not self.errors:
            raise forms.ValidationError(
                "Elige un certificado existente o sube uno.",
            )
        if upload and not _is_certificate_file(upload.name):
            self.add_error(
                "certificate_file",
                "El certificado debe ser un PDF o una imagen.",
            )
        return cleaned


class LiftingAccessoryAssignmentForm(forms.Form):
    """
    New delivery of an accessory.
    ---
    Nueva entrega de un accesorio.
    """

    start_date = forms.DateField(label="Fecha de entrega", widget=_DATE_WIDGET)
    notes = forms.CharField(
        required=False, label="Observaciones",
        widget=_small(forms.TextInput),
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible_person"] = _responsible_field(True)
        self.fields["machine"] = _machine_field(company)
        self.order_fields(
            ["responsible_person", "machine", "start_date", "notes"],
        )


class LiftingAccessoryReturnForm(forms.Form):
    """
    Return of an accessory (closes its open delivery).
    ---
    Devolución de un accesorio (cierra su entrega abierta).
    """

    end_date = forms.DateField(
        label="Fecha de devolución", widget=_DATE_WIDGET,
    )


class LiftingAccessoryReviewForm(forms.Form):
    """
    New review; the explicit expiry, if given, prevails over +12 months.
    ---
    Nueva revisión; la caducidad indicada, si la hay, prevalece sobre
    la fecha de revisión + 12 meses (decisión 5).
    """

    review_date = forms.DateField(
        label="Fecha de revisión", widget=_DATE_WIDGET,
    )
    explicit_expiry_date = forms.DateField(
        required=False, label="Caducidad indicada (opcional)",
        widget=_DATE_WIDGET,
        help_text="Si la indicas, prevalece sobre la revisión + 12 meses.",
    )
    source_entry = DocumentChoiceField(
        queryset=DocumentIndexEntry.objects.none(),
        required=False,
        label="Documento de la revisión",
        empty_label="-- Sin documento --",
        widget=_small(forms.Select),
    )

    def __init__(self, *args, with_document=True, **kwargs):
        super().__init__(*args, **kwargs)
        if with_document:
            self.fields["source_entry"].queryset = service.review_candidates()
        else:
            del self.fields["source_entry"]

    def clean(self):
        """
        The explicit expiry can never be before the review.
        ---
        La caducidad indicada nunca puede ser anterior a la revisión.
        """
        cleaned = super().clean()
        review_date = cleaned.get("review_date")
        expiry = cleaned.get("explicit_expiry_date")
        if review_date and expiry and expiry < review_date:
            self.add_error(
                "explicit_expiry_date",
                "La caducidad no puede ser anterior a la revisión.",
            )
        return cleaned


class LiftingAccessoryTypeForm(forms.ModelForm):
    """
    Create or edit one accessory type of the catalogue.
    ---
    Alta o edición de un tipo de accesorio del catálogo.
    """

    class Meta:
        model = LiftingAccessoryType
        fields = ["label", "code", "display_order"]
        widgets = {
            "label": _small(forms.TextInput),
            "code": _small(forms.TextInput),
            "display_order": _small(forms.NumberInput, min="0"),
        }

    def clean_code(self):
        """
        Codes are stored upper-case with underscores, like the seeded ones.
        ---
        Los códigos se guardan en mayúsculas con guiones bajos, como los
        sembrados (ESLINGA_CABLE_ACERO...).
        """
        code = (self.cleaned_data.get("code") or "").strip().upper()
        return "_".join(code.split())

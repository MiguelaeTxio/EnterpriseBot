# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/forms_lifting_accessories.py
"""
H30 (S121). Forms of the "Accesorios de elevación" tab of the
Documentation hub: accessory, certificate, delivery, return, review and
accessory type.

---

H30 (S121). Formularios de la pestaña "Accesorios de elevación" del hub
de Documentación: accesorio, certificado, entrega, devolución, revisión
y tipo de accesorio.

Criterio de Miguel Ángel (S121): el supervisor nunca ve nombres de
archivo ni rutas del bucket, ni enlaza documentos a mano. Lo que ya
existe en el bucket lo tipa y enlaza el sistema; el supervisor solo
sube el documento cuando da de alta algo nuevo. Por eso aquí no hay
ningún selector de documentos: solo campos de subida.
"""

from django import forms
from django.urls import reverse

from document_explorer.models import (
    LiftingAccessory,
    LiftingAccessoryModel,
    LiftingAccessoryType,
    PersonIdentity,
)
from fleet.cost_center_search import resolve_cost_center

_DATE_WIDGET = forms.DateInput(
    format="%Y-%m-%d",
    attrs={"type": "date", "class": "form-control form-control-sm"},
)
_ACCEPTED_EXTENSIONS = ("pdf", "jpg", "jpeg", "png")


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


def _file_field(label, required):
    """
    PDF or image upload field.
    ---
    Campo de subida de PDF o imagen.
    """
    return forms.FileField(
        required=required,
        label=label,
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control form-control-sm",
            "accept": ".pdf,.jpg,.jpeg,.png",
        }),
    )


def _check_extension(form, field_name):
    """
    Add an error if the uploaded file is not a PDF or an image.
    ---
    Añade un error si el archivo subido no es un PDF o una imagen.
    """
    upload = form.cleaned_data.get(field_name)
    if upload and (
        upload.name.rsplit(".", 1)[-1].lower() not in _ACCEPTED_EXTENSIONS
    ):
        form.add_error(field_name, "Debe ser un PDF o una imagen.")


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


class LiftingAccessoryForm(forms.ModelForm):
    """
    Create or edit one accessory. Creating means a NEW accessory (one
    that does not exist yet), so its certificate upload is mandatory.
    ---
    Alta o edición de un accesorio. El alta es para un accesorio NUEVO
    (que no existe todavía), así que subir su certificado es
    obligatorio. El alta no incluye ninguna entrega: entregar es un acto
    aparte (Miguel Ángel, S121).
    """

    class Meta:
        model = LiftingAccessory
        fields = [
            "model", "accessory_type", "identifier", "traceability",
            "description", "dimensions", "working_load_kg", "standard",
            "manufacturer", "supply_date",
        ]
        widgets = {
            "model": _small(forms.Select),
            "accessory_type": _small(forms.Select),
            "identifier": _small(forms.TextInput),
            "traceability": _small(forms.TextInput),
            "description": _small(forms.TextInput),
            "dimensions": _small(forms.TextInput),
            "working_load_kg": _small(forms.NumberInput, min="0"),
            "standard": _small(forms.TextInput),
            "manufacturer": _small(forms.TextInput),
            "supply_date": _DATE_WIDGET,
        }

    def __init__(self, *args, company=None, is_create=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["accessory_type"].queryset = (
            LiftingAccessoryType.objects.filter(is_active=True)
            | LiftingAccessoryType.objects.filter(
                pk=self.instance.accessory_type_id,
            )
        ).distinct()
        self.fields["accessory_type"].empty_label = "-- Elegir tipo --"
        # S121: el modelo rellena tipo, medidas, carga y norma; con modelo
        # el tipo no hace falta elegirlo aparte.
        self.fields["accessory_type"].required = False
        self.fields["accessory_type"].help_text = (
            "Solo si no eliges modelo (el modelo ya lo lleva)."
        )
        self.fields["model"].queryset = (
            LiftingAccessoryModel.objects.filter(is_active=True)
            | LiftingAccessoryModel.objects.filter(pk=self.instance.model_id)
        ).distinct().select_related("accessory_type")
        self.fields["model"].empty_label = "-- Elegir modelo --"
        self.fields["model"].help_text = (
            "Rellena tipo, medidas, carga y norma si los dejas en blanco."
        )
        if is_create:
            self.fields["certificate_file"] = _file_field(
                "Certificado del fabricante (PDF o foto)", required=True,
            )

    def clean(self):
        """
        Unique (company, type, identifier); certificate PDF or image.
        ---
        Único por (empresa, tipo, nº) -- la restricción de BD incluye la
        empresa, que no es campo del formulario, así que se comprueba
        aquí para dar un error legible en vez de un IntegrityError. Y el
        certificado, PDF o imagen.
        """
        cleaned = super().clean()
        model = cleaned.get("model")
        if model is not None:
            if (cleaned.get("accessory_type") is not None
                    and cleaned["accessory_type"] != model.accessory_type):
                self.add_error(
                    "accessory_type",
                    "El tipo no coincide con el del modelo elegido.",
                )
            cleaned["accessory_type"] = model.accessory_type
            for field in ("dimensions", "working_load_kg", "standard"):
                if cleaned.get(field) in (None, ""):
                    cleaned[field] = getattr(model, field)
        elif cleaned.get("accessory_type") is None:
            self.add_error(
                "accessory_type", "Elige un modelo o, si no hay, un tipo.",
            )
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
        if "certificate_file" in self.fields:
            _check_extension(self, "certificate_file")
        return cleaned


class LiftingAccessoryCertificateForm(forms.Form):
    """
    Upload one more certificate of an accessory (e.g. a renewed one).
    ---
    Subir otro certificado de un accesorio (p. ej. uno renovado).
    """

    certificate_file = _file_field(
        "Subir certificado (PDF o foto)", required=True,
    )

    def clean(self):
        cleaned = super().clean()
        _check_extension(self, "certificate_file")
        return cleaned


class LiftingAccessoryAssignmentForm(forms.Form):
    """
    Delivery: to which cost centre and to whom -- both mandatory.
    ---
    Entrega: a qué centro de gasto y a quién -- ambos obligatorios
    (Miguel Ángel, S121). El centro de gasto se escribe por código y se
    elige en el desplegable de coincidencias, el mismo sistema que el
    parte diario digital (fleet.cost_center_search).
    """

    cost_center = forms.CharField(
        label="Centro de gasto",
        widget=forms.TextInput(attrs={
            "class": "form-control form-control-sm cdg-search",
            "placeholder": "Código de máquina o CdG",
            "autocomplete": "off",
        }),
    )
    start_date = forms.DateField(label="Fecha de entrega", widget=_DATE_WIDGET)
    notes = forms.CharField(
        required=False, label="Observaciones",
        widget=_small(forms.TextInput),
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["cost_center"].widget.attrs["data-cdg-url"] = reverse(
            "panel:lifting_accessory_cost_centers",
        )
        self.fields["responsible_person"] = PersonChoiceField(
            queryset=PersonIdentity.objects.filter(
                is_active_employee=True,
            ).order_by("first_surname", "second_surname", "given_name"),
            label="Entregado a (responsable)",
            empty_label="-- Elegir trabajador --",
            widget=_small(forms.Select),
        )
        self.order_fields(
            ["cost_center", "responsible_person", "start_date", "notes"],
        )

    def clean_cost_center(self):
        """
        Resolve the typed code to an active cost centre of the company.
        ---
        Resuelve el código escrito a un centro de gasto activo de la
        empresa; si no existe, error legible.
        """
        machine = resolve_cost_center(
            self.company, self.cleaned_data.get("cost_center"),
        )
        if machine is None:
            raise forms.ValidationError(
                "No existe ningún centro de gasto activo con ese código.",
            )
        return machine


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
    la fecha de revisión + 12 meses. Su documento, si lo hay, se sube
    (nunca se elige de una lista de archivos).
    """

    review_date = forms.DateField(
        label="Fecha de revisión", widget=_DATE_WIDGET,
    )
    explicit_expiry_date = forms.DateField(
        required=False, label="Caducidad indicada (opcional)",
        widget=_DATE_WIDGET,
        help_text="Si la indicas, prevalece sobre la revisión + 12 meses.",
    )

    def __init__(self, *args, with_document=True, **kwargs):
        super().__init__(*args, **kwargs)
        if with_document:
            self.fields["review_file"] = _file_field(
                "Documento de la revisión (opcional)", required=False,
            )

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
        if "review_file" in self.fields:
            _check_extension(self, "review_file")
        return cleaned


class LiftingAccessoryModelForm(forms.ModelForm):
    """
    Create or edit one catalogue model.
    ---
    Alta o edición de un modelo del catálogo.
    """

    class Meta:
        model = LiftingAccessoryModel
        fields = [
            "accessory_type", "name", "dimensions", "working_load_kg",
            "standard", "display_order",
        ]
        widgets = {
            "accessory_type": _small(forms.Select),
            "name": _small(forms.TextInput),
            "dimensions": _small(forms.TextInput),
            "working_load_kg": _small(forms.NumberInput, min="0"),
            "standard": _small(forms.TextInput),
            "display_order": _small(forms.NumberInput, min="0"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["accessory_type"].queryset = (
            LiftingAccessoryType.objects.filter(is_active=True)
            | LiftingAccessoryType.objects.filter(
                pk=self.instance.accessory_type_id,
            )
        ).distinct()
        self.fields["accessory_type"].empty_label = "-- Tipo --"
        self.fields["display_order"].required = False

    def clean_display_order(self):
        """
        Empty order means 0 (the quick create form does not send it).
        ---
        Orden vacío es 0 (el alta rápida del panel no lo envía).
        """
        return self.cleaned_data.get("display_order") or 0


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

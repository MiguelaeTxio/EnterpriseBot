# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/budgets/driver_qualification.py
"""
H37 (S133). Whether a driver can take a machine (licence, CAP, crane).

---

H37 (S133). Si un conductor puede llevar una máquina según lo que
exige su tipo (`MachineDriverRequirement`): clases del permiso de
conducción en vigor, leídas del carné más reciente con matriz (mismo
criterio que la documentación requerida de H30) y documentos en vigor
(CAP, carné de gruista). Miguel Ángel, S133: "tenemos los permisos de
conducción para poder determinar a quien podemos enviar según su
permiso".

Lo que falta se devuelve como frases cortas para Alia y el registro.
Un tipo de máquina sin requisitos configurados no exige nada.
"""
import datetime

from django.contrib.contenttypes.models import ContentType

from budgets.models import MachineDriverRequirement

BUCKET = "cgs_grupo_alvarez"
DRIVING_CARD_CODE = "CARNET_CONDUCIR"


class Checker:
    """
    Qualification checks for one company, with caches.

    ---

    Comprobaciones de una empresa, con lo leído guardado para no
    repetir consultas al revisar todos los conductores y máquinas.
    """

    def __init__(self, company, today=None):
        self.today = today or datetime.date.today()
        self.requirements = {
            requirement.machine_type_name.strip().upper(): requirement
            for requirement in MachineDriverRequirement.objects.filter(
                company=company, is_active=True,
            ).prefetch_related(
                "required_categories", "required_documents__document_types",
            )
        }
        self._people = {}

    def requirement_for(self, machine):
        """
        Requirement of the machine type, or None.

        ---

        Requisito del tipo de la máquina, o None si no hay.
        """
        return self.requirements.get(
            (getattr(machine, "type_name", "") or "").strip().upper(),
        )

    def _person_data(self, person):
        """
        Licence classes and documents of a person, with their expiry.

        ---

        Clases del permiso (código -> caducidad o None) del carné más
        reciente con matriz, y documentos (pk del tipo -> caducidad más
        lejana o None si no caducan) de la persona.
        """
        if person.pk in self._people:
            return self._people[person.pk]
        from document_explorer.models import (
            DocumentIndexEntry,
            DrivingLicenceGrant,
        )
        from document_explorer.required_documentation_service import (
            latest_driving_card,
        )

        entries = list(DocumentIndexEntry.objects.filter(
            bucket=BUCKET,
            domain_content_type=ContentType.objects.get_for_model(
                type(person),
            ),
            domain_object_id=person.pk,
            entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            document_type__isnull=False,
        ).select_related("document_type"))
        cards = [
            entry for entry in entries
            if entry.document_type.code == DRIVING_CARD_CODE
        ]
        grants = list(DrivingLicenceGrant.objects.filter(
            entry__in=cards,
        ).select_related("category"))
        card = latest_driving_card(
            cards, frozenset(grant.entry_id for grant in grants),
        )
        classes = {
            grant.category.code: grant.expiry_date
            for grant in grants
            if card is not None and grant.entry_id == card.pk
        }
        documents = {}
        for entry in entries:
            key = entry.document_type_id
            if key not in documents:
                documents[key] = entry.expiry_date
            elif documents[key] is not None and (
                entry.expiry_date is None or entry.expiry_date > documents[key]
            ):
                documents[key] = entry.expiry_date
        self._people[person.pk] = (classes, documents)
        return classes, documents

    def missing(self, driver, machine):
        """
        What the driver lacks for the machine (empty list: can take it).

        ---

        Lo que le falta al conductor para la máquina, en frases cortas
        ("sin permiso CE", "CAP caducado el 03/05/2026"). Lista vacía:
        puede llevarla.
        """
        requirement = self.requirement_for(machine)
        if requirement is None:
            return []
        person = getattr(driver, "person_identity", None)
        if person is None:
            return ["sin ficha de persona para comprobar permisos"]
        classes, documents = self._person_data(person)
        problems = []
        for category in requirement.required_categories.all():
            if category.code not in classes:
                problems.append("sin permiso %s" % category.code)
            elif classes[category.code] and (
                classes[category.code] < self.today
            ):
                problems.append("permiso %s caducado el %s" % (
                    category.code, classes[category.code].strftime("%d/%m/%Y"),
                ))
        for document in requirement.required_documents.all():
            expiries = [
                documents[document_type.pk]
                for document_type in document.document_types.all()
                if document_type.pk in documents
            ]
            if not expiries:
                problems.append("sin %s" % document.name)
            elif None not in expiries and max(expiries) < self.today:
                problems.append("%s caducado el %s" % (
                    document.name, max(expiries).strftime("%d/%m/%Y"),
                ))
        return problems

    def machine_types_for(self, driver):
        """
        Machine types the driver can take (with requirements set).

        ---

        Tipos de máquina que el conductor puede llevar, de los que
        tienen requisitos configurados.
        """
        class _Machine:
            def __init__(self, type_name):
                self.type_name = type_name

        return sorted(
            requirement.machine_type_name
            for requirement in self.requirements.values()
            if not self.missing(
                driver, _Machine(requirement.machine_type_name),
            )
        )

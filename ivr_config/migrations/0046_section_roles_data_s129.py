# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0046_section_roles_data_s129.py
"""
H24 (S129). The two real sections of the new positions get their
signup role: "Guardas" -> NIGHTGUARD, "Administración-Proveedores" ->
OFFICE. Only touches them while they still hold the old default
(WORKSHOP), so a value set by hand is never overwritten. The rest can
be changed from the panel (Secciones > editar).
---
H24 (S129). Las dos secciones reales de los puestos nuevos reciben su
rol de alta: "Guardas" -> NIGHTGUARD, "Administración-Proveedores" ->
OFFICE. Solo si siguen con el valor por defecto antiguo (WORKSHOP), para
no pisar nunca uno puesto a mano. El resto se cambia desde el panel
(Secciones > editar).
"""
from django.db import migrations

ROLES_BY_SECTION = {
    "Guardas": "NIGHTGUARD",
    "Administración-Proveedores": "OFFICE",
}


def forwards(apps, schema_editor):
    Section = apps.get_model("ivr_config", "Section")
    for name, role in ROLES_BY_SECTION.items():
        Section.objects.filter(name=name, default_role="WORKSHOP").update(
            default_role=role,
        )


def backwards(apps, schema_editor):
    Section = apps.get_model("ivr_config", "Section")
    for name, role in ROLES_BY_SECTION.items():
        Section.objects.filter(name=name, default_role=role).update(
            default_role="WORKSHOP",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0045_worker_roles_s129"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

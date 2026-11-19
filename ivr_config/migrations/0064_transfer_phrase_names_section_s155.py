# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0064_transfer_phrase_names_section_s155.py
"""
S155: la frase previa a la transferencia dice con quién se pasa.

En los flujos ya guardados solo se sustituye esa línea, para conservar
lo que se haya editado a mano en el resto del texto.
"""
from django.db import migrations

OLD = (
    "Cuando vayas a ejecutar una transferencia al responsable, SIEMPRE\n"
    "pronuncia antes: \"Un momento por favor, no se retire.\""
)


def _new(section_name):
    return (
        "Cuando vayas a ejecutar una transferencia al responsable, SIEMPRE\n"
        "di antes con quién le pasas: \"Le paso con la persona responsable "
        f"de {section_name}. Un momento, por favor, no se retire.\""
    )


def forwards(apps, schema_editor):
    Section = apps.get_model("ivr_config", "Section")
    for section in Section.objects.exclude(call_flow=None).select_related(
            "call_flow"):
        flow = section.call_flow
        if OLD in flow.system_instruction:
            flow.system_instruction = flow.system_instruction.replace(
                OLD, _new(section.name))
            flow.save(update_fields=["system_instruction"])


def backwards(apps, schema_editor):
    Section = apps.get_model("ivr_config", "Section")
    for section in Section.objects.exclude(call_flow=None).select_related(
            "call_flow"):
        flow = section.call_flow
        new = _new(section.name)
        if new in flow.system_instruction:
            flow.system_instruction = flow.system_instruction.replace(
                new, OLD)
            flow.save(update_fields=["system_instruction"])


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0063_role_services_s149"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

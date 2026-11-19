# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0065_transfer_announced_by_system_s155.py
"""
S155: el aviso de transferencia lo dice Twilio, no Gemini.

En los flujos ya guardados se sustituye solo el bloque de la
transferencia, para conservar lo editado a mano en el resto del texto.
"""
from django.db import migrations

NEW = (
    "Cuando vayas a transferir al responsable, NO anuncies la\n"
    "transferencia: invoca la función directamente. El sistema le dice\n"
    "al llamante con quién le pasa."
)


def _old(section_name):
    return (
        "Cuando vayas a ejecutar una transferencia al responsable, SIEMPRE\n"
        "di antes con quién le pasas: \"Le paso con la persona responsable "
        f"de {section_name}. Un momento, por favor, no se retire.\"\n"
        "NUNCA ejecutes la transferencia sin despedirte verbalmente del "
        "llamante."
    )


def _flows(apps):
    Section = apps.get_model("ivr_config", "Section")
    return Section.objects.exclude(call_flow=None).select_related(
        "call_flow")


def forwards(apps, schema_editor):
    for section in _flows(apps):
        flow, old = section.call_flow, _old(section.name)
        if old in flow.system_instruction:
            flow.system_instruction = flow.system_instruction.replace(
                old, NEW)
            flow.save(update_fields=["system_instruction"])


def backwards(apps, schema_editor):
    for section in _flows(apps):
        flow = section.call_flow
        if NEW in flow.system_instruction:
            flow.system_instruction = flow.system_instruction.replace(
                NEW, _old(section.name))
            flow.save(update_fields=["system_instruction"])


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0064_transfer_phrase_names_section_s155"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

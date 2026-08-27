# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0062_person_identity_audit_fixes_s74.py
"""
H31 (S74). Correcciones reales derivadas de la auditoría Excel vs BD
pedida explícitamente por Miguel Ángel tras detectar un caso de
identidad duplicada real (ficha de Alejandro García Luque en el
panel, S74). Fuente de verdad: EXEL_TRABAJADORES.xlsx entregado por
Miguel Ángel en esta misma sesión, comparado 1:1 (nombre + DNI)
contra los 58 trabajadores reales de las 4 hojas de plantilla.

Tres correcciones puntuales de apellido -- Miguel Ángel, decisión
explícita: "nos ceñimos a lo que ponga el Excel... es la fuente de la
verdad. Si luego hay que cambiarlo, lo cambiaremos luego":

1. pk=158 (dni=74852724Y): second_surname 'FUENTES' -> 'LUQUE'.
   Ver también la fusión de identidad duplicada más abajo -- esta
   fila es la que tiene el DNI real correcto.
2. pk=198 (dni=26301275Q): first_surname 'CORREA' -> 'CORREO'
   (Excel: "CORREO MUNHOZ, PAULO FRANCISCO").
3. pk=177 (dni=25695295V): first_surname 'ROSAS' -> 'ROSA' (Excel:
   "ROSA SANCHEZ, FCO. JOSE").

Fusión de identidad duplicada real -- Alejandro García Luque:
`PersonIdentity pk=96` (dni=74852725F, given_name='ANTONIO JESUS')
es un fantasma de captura: su DNI pasa la letra de control
(matemáticamente válido, LETTERS[74852725 % 23] == 'F') pero no
corresponde a ninguna persona real del Excel -- está exactamente a 1
dígito de distancia tanto del DNI real de Alejandro (74852724Y,
pk=158) como del de Manuel Ruiz Portillo (74852721A), confirmado por
comparación numérica en esta sesión. Los 87 `DocumentIndexEntry`
vinculados a pk=96 son documentos reales de Alejandro (la inmensa
mayoría de los propios nombres de archivo dicen literalmente "GARCIA
LUQUE, ALEJANDRO") que quedaron repartidos en una carpeta histórica
duplicada (`.../BAJAS/OPERARIOS BAJAS/GARCIA LUQUE,ANTONIO JESUS
(TR)/...`) en vez de la carpeta real
(`.../OPERARIOS/GARCIA LUQUE ALEJANDRO (TR)/...`, pk=158).

Esta migración SOLO repunta domain_object_id de DocumentIndexEntry y
person_id de EpiDelivery de pk=96 hacia pk=158 -- operación pura de
base de datos (directriz 4.12: blob_name nunca se toca). NO borra la
fila pk=96 -- Miguel Ángel pidió verificar los totales tras el
repunte antes de eliminarla, ver Comando S de verificación en el
registro de sesión S74.
"""
from django.db import migrations


def apply_audit_fixes(apps, schema_editor):
    PersonIdentity = apps.get_model("document_explorer", "PersonIdentity")
    DocumentIndexEntry = apps.get_model("document_explorer", "DocumentIndexEntry")
    EpiDelivery = apps.get_model("document_explorer", "EpiDelivery")
    ContentType = apps.get_model("contenttypes", "ContentType")

    # -- 1-3: correcciones puntuales de apellido, fuente Excel --
    PersonIdentity.objects.filter(dni="74852724Y").update(second_surname="LUQUE")
    PersonIdentity.objects.filter(dni="26301275Q").update(first_surname="CORREO")
    PersonIdentity.objects.filter(dni="25695295V").update(first_surname="ROSA")

    # -- Fusión de identidad duplicada: pk=96 (fantasma) -> pk=158 (real) --
    ghost = PersonIdentity.objects.filter(dni="74852725F").first()
    real = PersonIdentity.objects.filter(dni="74852724Y").first()
    if ghost is None or real is None:
        # No debería pasar -- ambos DNIs verificados reales en esta
        # sesión -- pero si el estado cambió entre sesiones, mejor no
        # romper el deploy que asumir en silencio.
        return

    ct = ContentType.objects.get_for_model(PersonIdentity)
    DocumentIndexEntry.objects.filter(
        domain_content_type=ct, domain_object_id=ghost.pk,
    ).update(domain_object_id=real.pk)
    EpiDelivery.objects.filter(person_id=ghost.pk).update(person_id=real.pk)


def noop_reverse(apps, schema_editor):
    """
    No se revierte -- reconstruir con certeza qué filas pertenecían a
    cada apellido/identidad antes de esta migración no es posible
    (esa es justo la razón de la corrección), mismo criterio que
    0033_merge_duplicate_types_s51.py.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0061_personidentity_company_user_s74"),
    ]

    operations = [
        migrations.RunPython(apply_audit_fixes, noop_reverse),
    ]

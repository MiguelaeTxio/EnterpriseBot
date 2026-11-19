# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0228_circular_alta_fichaje_panel_s149.py
# H24 (S149, sesión invasora): circular "Alta en el fichaje (ya con
# usuario del panel)" (Miguel Ángel, 18-19/11, Jerónimo: "otros usuarios
# que ya tengan usuario del panel y simplemente le damos el alta para
# los fichajes"). Es la de ALTA_FICHAJE sin la contraseña del DNI: entra
# con la suya. Va por la misma plantilla de WhatsApp ya aprobada
# (circular_notification). Se edita en la pestaña Circulares; si ya
# existe una con el mismo código, no se toca.
from django.db import migrations

CODE = "ALTA_FICHAJE_PANEL"
LABEL = "Alta en el fichaje (ya con usuario del panel)"
CONTENT = """
<p>Hola, {{trabajador.nombre_completo}}:</p>
<p>Desde hoy el registro de jornada se hace con el móvil. Para fichar
usas el mismo usuario y la misma contraseña con los que ya entras en el
panel.</p>
<p><strong>Tus datos de acceso</strong></p>
<ul>
<li>Usuario: <strong>{{trabajador.usuario}}</strong></li>
<li>Contraseña: <strong>la que ya usas para entrar en el panel</strong>
(no cambia).</li>
<li>Enlace para fichar: <strong>{{enlace.fichaje}}</strong></li>
</ul>
<p><strong>La primera vez (solo una vez)</strong></p>
<ol>
<li>Abre el enlace en tu móvil.</li>
<li>Si en ese móvil ya entras en el panel, la página de fichaje se abre
directamente. Si no, pulsa <strong>«Entrar en el panel»</strong> y
escribe tu usuario y tu contraseña de siempre.</li>
<li>Cuando te pregunte, marca este móvil como <strong>dispositivo de
confianza</strong>. Volverás a la página de fichaje.</li>
<li>En el menú del navegador, pulsa <strong>«Añadir a pantalla de
inicio»</strong> (o «Instalar aplicación»): te quedará el icono
<strong>Fichaje</strong> como una aplicación.</li>
<li>Cuando te pida permiso para la ubicación, pulsa
<strong>Permitir</strong>.</li>
</ol>
<p><strong>Cada día</strong></p>
<ul>
<li>Al empezar, abre <strong>Fichaje</strong> y pulsa el botón verde
<strong>«Fichar entrada»</strong>.</li>
<li>Al terminar, pulsa el botón rojo <strong>«Fichar salida»</strong>.</li>
<li>Si tu sección ficha por tipos (por ejemplo, desplazamiento,
presencia o trabajo efectivo), elige el tipo al entrar y, durante la
jornada, pulsa el nuevo tipo cada vez que cambies de actividad.</li>
<li>Sin cobertura también puedes fichar: se guarda en el móvil con la
hora a la que pulsaste y se envía solo al volver la conexión.</li>
<li>Si se te olvida fichar, usa <strong>«¿Se te olvidó fichar? Fichaje
manual»</strong> e indica el día y la hora. Quedará anotado como fichaje
manual.</li>
</ul>
<p>Si tienes cualquier problema para entrar o para fichar, escríbenos
por este mismo WhatsApp.</p>
<p>Un saludo.</p>
""".strip()


def create_circular(apps, schema_editor):
    catalog = apps.get_model("document_explorer", "DocumentTypeCatalog")
    if catalog.objects.filter(code=CODE).exists():
        return
    catalog.objects.create(
        code=CODE, label=LABEL, domain="PERSONAL", family="LABORAL",
        is_notification_template=True, requires_signature=False,
        content_html=CONTENT,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0227_docidx_domain_object_s153"),
    ]

    operations = [
        migrations.RunPython(create_circular, migrations.RunPython.noop),
    ]

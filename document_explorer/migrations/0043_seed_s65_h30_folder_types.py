# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0043_seed_s65_h30_folder_types.py
"""
H30 (S65). Alta de 4 tipos documentales nuevos, confirmados con
muestra real (una a tres por carpeta, contenido leido letra por
letra, nunca asumido por nombre de carpeta) sobre 6 carpetas de
DOC. PERSONAL identificadas sin tipo en S64 (ver anexo, bloque "HOJA
DE RUTA PARA LA SIGUIENTE SESION (S65)").

Confirmado con EnterpriseBot_001_GET.txt (consulta real contra
DocumentTypeCatalog en produccion, S65): ninguno de estos 4 codigos
existia ya en el catalogo. Solo aparecian CARNET_GRUISTA (PERSONAL,
ya activo -- cubre la carpeta RENOVACION CARNE DEGRUISTA sin alta
nueva) y GASTOS_TARJETA_COMBUSTIBLE (MACHINE -- gasto de tarjeta de
combustible de maquina, concepto distinto sin relacion real con
ENTREGA_MANUAL_COMBUSTIBLE pese a compartir la palabra "combustible").

- EVALUACION_RIESGO: confirmado con ALVAREZ_GEA.pdf (S65) -- "ENTREGA
  DE EVALUACION DE RIESGO" firmada por el trabajador, GRUAS ADOLFO
  ALVAREZ S.L. Family PRL_FORMACION, mismo bucket que EPIS/
  ENTREGA_INFORMACION/AUTORIZACION_USO_MAQUINARIA (migracion 0028).

- ENTREGA_MANUAL_COMBUSTIBLE: confirmado con
  ALHAMAR_AVELLANEDA_JUAN_M.docx (S65) -- "Manual suministro
  combustible y procedimiento ante situacion de emergencia
  entregados al trabajador", articulo 18 Ley 31/1995 PRL. Family
  PRL_FORMACION, mismo patron que ENTREGA_INFORMACION.

- AUTORIZACION_MEDIOS_COMUNICACION: confirmado con
  ANTONIO_MIGUEL_PEREZ_CASTILLA_FIRMADO.pdf (S65) -- "Comunicado de
  Autorizacion de Medios de Comunicacion" (telefono/email), firmado
  via Docuten por un trabajador de Asistencia y Gruas Granada, S.L.
  (confirmado por Miguel Angel: empresa del propio Grupo Alvarez, no
  fuga de otra empresa). Family ADMINISTRATIVO, mismo bucket que
  SOLICITUD_ADMINISTRATIVA.

- AUTORIZACION_LIBRO_SUBCONTRATA: confirmado con 3 muestras reales
  distintas (S65) -- texto identico en las tres, "AUTORIZACION FIRMA
  LIBRO SUBCONTRATACION", el administrador (Adolfo o Alejandro
  Alvarez Diaz) autoriza a un trabajador concreto a firmar el Libro
  de Subcontratacion de una obra en representacion de la empresa.
  Family ADMINISTRATIVO.

  ADVERTENCIA REAL PARA RESOLUCION DE DOMINIO (no aplica en esta
  migracion, deja constancia para la sesion que la implemente): el
  nombre de archivo NO es fiable para identificar a la persona
  autorizada -- de las 3 muestras, 2 no coinciden entre nombre de
  archivo y persona real autorizada dentro del texto (ej.
  "Autorizacion_ALVAREZ_GEA.docx" autoriza en realidad a Jose Carlos
  Martinez Segura, no a nadie con apellido Alvarez Gea -- mismo
  patron de falso match ya conocido de S64). La persona debe
  resolverse leyendo el cuerpo real del texto ("A D. ___ con DNI:
  ___"), nunca por nombre de archivo/carpeta -- requiere Fase B
  (OCR/lectura real), no heuristica de Fase A.

Todos con tracks_expiry=False (declaraciones puntuales fechadas, sin
version "vigente" que sustituya a la anterior via
vigencia_service.evaluate_substitution() -- mismo criterio que
AUTONOMO/CERT_LIMITACIONES, migraciones 0039/0040).

RETENCIONES queda deliberadamente fuera de esta migracion: confirmado
como certificado de retenciones IRPF real, pero el archivo de
muestra agrupa a mas de 25 trabajadores distintos en un unico PDF
(mismo problema estructural que los dossiers de
RECONOCIMIENTO_MEDICO) -- requiere una herramienta de split antes de
poder indexarse 1:1 contra PersonIdentity, pendiente de diseno,
decision explicita de Miguel Angel en S65 de no resolverlo en esta
sesion.
"""
from django.db import migrations

NEW_TYPES = [
    {
        "code": "EVALUACION_RIESGO",
        "label": "Entrega de evaluación de riesgo",
        "domain": "PERSONAL",
        "family": "PRL_FORMACION",
        "tracks_expiry": False,
    },
    {
        "code": "ENTREGA_MANUAL_COMBUSTIBLE",
        "label": "Entrega de manual de combustible y emergencias",
        "domain": "PERSONAL",
        "family": "PRL_FORMACION",
        "tracks_expiry": False,
    },
    {
        "code": "AUTORIZACION_MEDIOS_COMUNICACION",
        "label": "Autorización de medios de comunicación",
        "domain": "PERSONAL",
        "family": "ADMINISTRATIVO",
        "tracks_expiry": False,
    },
    {
        "code": "AUTORIZACION_LIBRO_SUBCONTRATA",
        "label": "Autorización firma libro de subcontratación",
        "domain": "PERSONAL",
        "family": "ADMINISTRATIVO",
        "tracks_expiry": False,
    },
]


def seed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    for spec in NEW_TYPES:
        DocumentTypeCatalog.objects.get_or_create(
            code=spec["code"],
            defaults={
                "label": spec["label"],
                "domain": spec["domain"],
                "family": spec["family"],
                "tracks_expiry": spec["tracks_expiry"],
                "is_active": True,
            },
        )


def unseed_new_types(apps, schema_editor):
    DocumentTypeCatalog = apps.get_model(
        "document_explorer", "DocumentTypeCatalog",
    )
    DocumentTypeCatalog.objects.filter(
        code__in=[spec["code"] for spec in NEW_TYPES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0042_corregir_domain_both_s64"),
    ]

    operations = [
        migrations.RunPython(seed_new_types, unseed_new_types),
    ]

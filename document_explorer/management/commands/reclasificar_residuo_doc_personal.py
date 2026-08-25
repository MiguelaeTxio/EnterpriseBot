# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/reclasificar_residuo_doc_personal.py
"""
H30 (S68) -- Punto 2 de la hoja de ruta: continua el residuo de
316/318 archivos sin tipo de `DOC. PERSONAL/PERSONAL/` con los
patrones de S67, confirmados uno a uno con Miguel Angel en S68 contra
nombres de archivo reales (nunca adivinados por la palabra sola).

Crea 8 tipos nuevos en `DocumentTypeCatalog` (ninguno existia --
verificado en S68) y asigna `document_type` a los archivos que
encajan en cada patron.

Caso especial confirmado a mano en S68: dentro del grupo "PLANTILLA"
(3 archivos), 2 son plantilla generica real de empresa sin persona,
pero el tercero (`...PETRU IORDACHI...`) resulto ser, verificado con
la propia imagen del documento, una entrega de informacion de riesgos
(RYMPE) ya firmada por un transportista real -- no una plantilla en
blanco. Va a `ENTREGA_INFORMACION` (tipo ya existente en el catalogo,
no se crea de nuevo), excluido a mano del grupo PLANTILLA.

DRY-RUN POR DEFECTO. Con --apply escribe de verdad.
"""
import re

from django.core.management.base import BaseCommand

from document_explorer.models import DocumentIndexEntry, DocumentTypeCatalog

TIPOS_NUEVOS = [
    # code, label, domain, family
    ("PLANTILLA", "Plantilla de empresa", DocumentTypeCatalog.DOMAIN_COMPANY, DocumentTypeCatalog.FAMILY_OTROS_DOCUMENTOS),
    ("CERTIF_TRABAJO_COLEGIO", "Certificado de trabajo (colegio/guardería)", DocumentTypeCatalog.DOMAIN_PERSONAL, DocumentTypeCatalog.FAMILY_LABORAL),
    ("COMUNICACION_JORNADA", "Comunicación de ampliación/disminución de jornada", DocumentTypeCatalog.DOMAIN_PERSONAL, DocumentTypeCatalog.FAMILY_LABORAL),
    ("FORMACION_ITC_MINERA", "Formación/reciclaje ITC minería", DocumentTypeCatalog.DOMAIN_PERSONAL, DocumentTypeCatalog.FAMILY_PRL_FORMACION),
    ("CERTIF_DISCAPACIDAD", "Certificado/tarjeta de discapacidad", DocumentTypeCatalog.DOMAIN_PERSONAL, DocumentTypeCatalog.FAMILY_SALUD_BAJAS_PERSONA),
    ("NIE", "NIE (Número de Identidad de Extranjero)", DocumentTypeCatalog.DOMAIN_PERSONAL, DocumentTypeCatalog.FAMILY_IDENTIDAD_PERSONAL),
    ("COMUNICACION_FALTA", "Comunicación de falta disciplinaria", DocumentTypeCatalog.DOMAIN_PERSONAL, DocumentTypeCatalog.FAMILY_LABORAL),
    ("LIBRO_FAMILIA", "Libro de familia", DocumentTypeCatalog.DOMAIN_PERSONAL, DocumentTypeCatalog.FAMILY_IDENTIDAD_PERSONAL),
]

# etiqueta interna -> (palabras clave, code destino)
PATRONES = [
    ("COLEGIO/GUARDERIA", ["COLEGIO", "GUARDERIA"], "CERTIF_TRABAJO_COLEGIO"),
    ("HORARIO/JORNADA", ["HORARIO", "JORNADA"], "COMUNICACION_JORNADA"),
    ("ITC/MINAS/MINERIA/RECICLADO", ["ITC", "MINAS", "MINERIA", "RECICLADO"], "FORMACION_ITC_MINERA"),
    ("DISCAPACIDAD", ["DISCAPACIDAD"], "CERTIF_DISCAPACIDAD"),
    ("NIE", ["NIE"], "NIE"),
    ("FALTA", ["FALTA"], "COMUNICACION_FALTA"),
    ("LIBRO", ["LIBRO"], "LIBRO_FAMILIA"),
    ("PLANTILLA", ["PLANTILLA"], "PLANTILLA"),
]

# Confirmado a mano en S68 contra el documento real -- ver docstring.
FORZAR_TIPO = {"Plantilla_RYMP TRANSPORTE V4_897512981 PETRU IORDACHI 1.pdf": "ENTREGA_INFORMACION"}


def _contiene_palabra(nombre_up, palabra):
    # Bug real detectado en dry-run S68: subcadena simple sin límite
    # de palabra hacía que "NIE" cazara "DANIEL" (D-A-NIE-L), colando
    # como falsos positivos un documento COVID y uno legal
    # ("IND.ORDINARIO"). \b respeta límites de palabra de verdad --
    # pero regex trata "_" como carácter de palabra, así que
    # "..._DE_JORNADA_1..." no tenía frontera antes de "JORNADA" y
    # se perdían archivos reales con guion bajo como separador
    # (segundo bug real, mismo dry-run S68). Se normaliza "_" a
    # espacio antes de aplicar el límite de palabra.
    normalizado = nombre_up.replace("_", " ")
    return re.search(r"\b%s\b" % re.escape(palabra), normalizado) is not None


class Command(BaseCommand):
    help = (
        "H30 (S68) Punto 2 -- crea los 8 tipos nuevos confirmados y "
        "reclasifica el residuo real de DOC. PERSONAL/PERSONAL. "
        "Dry-run por defecto, --apply para escribir de verdad."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Escribe de verdad. Sin esta flag, solo informa.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]

        for code, label, domain, family in TIPOS_NUEVOS:
            existe = DocumentTypeCatalog.objects.filter(code=code).exists()
            if existe:
                self.stdout.write("YA EXISTE, no se toca: %s" % code)
                continue
            if apply_changes:
                DocumentTypeCatalog.objects.create(
                    code=code, label=label, domain=domain, family=family,
                )
                self.stdout.write("TIPO CREADO: %s (%s)" % (code, label))
            else:
                self.stdout.write("CREARIA TIPO: %s (%s / %s / %s)" % (code, label, domain, family))

        qs = DocumentIndexEntry.objects.filter(
            bucket="cgs_grupo_alvarez", entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            parent_path__startswith="DOC. PERSONAL/PERSONAL/",
            document_type__isnull=True,
        ).exclude(
            parent_path__startswith="DOC. PERSONAL/PERSONAL/BAJAS/",
        ).exclude(
            parent_path__icontains="/BAJAS/",
        ).only("id", "parent_path", "name")

        pks_por_tipo = {}
        for entry in qs.iterator():
            if entry.name in FORZAR_TIPO:
                pks_por_tipo.setdefault(FORZAR_TIPO[entry.name], []).append(entry.pk)
                self.stdout.write(
                    "CLASIFICAR (forzado a mano, ver docstring): %s -> %s"
                    % (entry.name, FORZAR_TIPO[entry.name])
                )
                continue
            nombre_up = entry.name.upper()
            for etiqueta, palabras, code in PATRONES:
                if any(_contiene_palabra(nombre_up, p) for p in palabras):
                    pks_por_tipo.setdefault(code, []).append(entry.pk)
                    self.stdout.write("CLASIFICAR (%s): %s -> %s" % (etiqueta, entry.name, code))
                    break

        totales = {"clasificados": 0, "sin_cambios": 0}
        for code, pks in pks_por_tipo.items():
            totales["clasificados"] += len(pks)
            if apply_changes:
                tipo = DocumentTypeCatalog.objects.get(code=code)
                n = DocumentIndexEntry.objects.filter(pk__in=pks).update(document_type=tipo)
                self.stdout.write("APLICADO %s: %d archivos" % (code, n))

        self.stdout.write("=== RESUMEN (%s) ===" % (
            "APLICADO" if apply_changes else "DRY-RUN, nada escrito"
        ))
        for code, pks in pks_por_tipo.items():
            self.stdout.write("    %s: %d archivos" % (code, len(pks)))
        self.stdout.write("    TOTAL clasificados: %d" % totales["clasificados"])

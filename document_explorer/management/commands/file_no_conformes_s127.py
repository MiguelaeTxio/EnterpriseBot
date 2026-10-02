# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/management/commands/file_no_conformes_s127.py
"""
H30 (S127). Human review of NO CONFORMES/CLASIFICACION, applied.

---

H30 (S127). Aplica la revisión humana de NO CONFORMES/CLASIFICACION
(Miguel Ángel: "No dejes trabajo visto sin hacer"). Cada archivo tiene
aquí un destino decidido a la vista de lo que Gemini leyó en su pasada
del H28 (registro SENT_NO_CONFORMES), de su nombre y, en los dudosos,
de su primera página:

- EMPRESA: a su subcarpeta de DOC. EMPRESA (movimiento virtual).
- PERSONA / MAQUINA: a la ficha de su dueño con
  `classification_service.file_entry_manually` (mismos pasos que el
  pipeline: nombre canónico, carpeta, tipo, vínculo). Casi todos
  fallaron en el H28 por un DNI mal leído ("revisar a mano"), por un
  429 de Gemini o por dominio forzado por la carpeta de origen.
- Copia exacta de algo ya archivado (misma huella CRC32C y tamaño):
  a la papelera en vez de archivar un duplicado.
- PAPELERA: lo que Miguel Ángel mandó tirar (42871, 42413) y basura
  evidente (52204, acceso directo de Windows).

Lo que no aparece aquí se queda en NO CONFORMES/CLASIFICACION para la
siguiente revisión. Sin --apply solo informa; idempotente (solo toca
archivos que siguen vivos en su carpeta de origen).
"""
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from document_explorer.buckets import (
    MANUAL_USO_FOLDER, NO_CONFORMES_PREFIX, PRIMARY_BUCKET,
)
from document_explorer import archive_service
from document_explorer.classification_service import (
    file_entry_manually, resolve_duplicate_of_filed_document,
    resolve_or_create_person_identity, trash_dossier_entry,
)
from document_explorer.models import (
    DocumentIndexEntry, DocumentTypeCatalog, PersonIdentity,
)
from document_explorer.subject_upload_service import upload_subject_document
from document_explorer.move_service import move_entries
from fleet.models import MachineAsset
from spare_parts.gcs_service import download_bytes

SOURCE = NO_CONFORMES_PREFIX.rstrip("/")
COMPANY = "DOC. EMPRESA"

# pk -> carpeta (movimiento virtual, sin tipo ni dueño).
MOVES = {
    42856: COMPANY + "/FISCAL Y CONTABILIDAD",   # Balance GRA 2025
    42866: COMPANY + "/FISCAL Y CONTABILIDAD",   # Modelo 200 2024
    42867: COMPANY + "/FISCAL Y CONTABILIDAD",   # Modelo 303 2026 1T
    42868: COMPANY + "/FISCAL Y CONTABILIDAD",   # Modelo 390 2025
    42860: COMPANY + "/SOCIETARIO",              # Escritura objeto social
    42851: COMPANY + "/BANCOS Y FINANCIACION",   # Contrato BMW Bank
    42863: COMPANY + "/BANCOS Y FINANCIACION",   # Financiera doc. empresas
    42869: COMPANY + "/BANCOS Y FINANCIACION",   # Cuenta Santander Automotor
    42870: COMPANY + "/BANCOS Y FINANCIACION",   # Certificado cuenta 6 meses
    52174: COMPANY + "/SEGUROS",                 # Contrato Mapfre Transgrual
    49932: COMPANY + "/TACOGRAFOS",              # Descargas de tarjetas
    42905: MANUAL_USO_FOLDER,                    # Especificaciones JLG 520AJ
    # Segunda revisión (S127, primera página abierta):
    42660: COMPANY + "/SEGUROS",       # Recibo Mapfre a cargo de GRA
    43183: COMPANY + "/FORMACION",     # Temario camión grúa autocargante
    43813: COMPANY + "/PLANTILLAS",    # Carta de baja voluntaria en blanco
    43981: COMPANY + "/PLANTILLAS",    # Certificado del taller en blanco
}

# Lo que ya estaba suelto en DOC. EMPRESA, a su subcarpeta.
COMPANY_TIDY = {
    20098: COMPANY + "/CIRCULARES",
    20099: COMPANY + "/CIRCULARES",
    20217: COMPANY + "/CIRCULARES",
    19986: COMPANY + "/RELACIONES LABORALES",
}

TRASH = {
    42871, 42413, 52204,
    # Tercera revisión (Miguel Ángel: "Papelera"): huérfanos sin dueño
    # posible -- 4 copias de una página interior de reconocimiento sin
    # nombre, 2 reversos de certificado de formación sin nombre, 2
    # números de cuenta sin titular y un PDF que no se puede abrir.
    42792, 42795, 43962, 44368, 44465, 45902, 48066, 49190, 52201,
}

# pk -> (persona pk, tipo, fecha). Originales antes que sus copias.
PERSONAL = [
    (42801, 151, "VACACIONES", "2026-07-09"),
    (42802, 151, "VACACIONES", "2026-08-10"),
    (44078, 151, "VACACIONES", "2026-07-09"),
    (44079, 151, "VACACIONES", "2026-08-10"),
    (42841, 221, "ALTA", "2026-08-21"),
    (42857, 4, "CARNET_CONDUCIR", "2021-11-02"),
    (43100, 85, "VACACIONES", "2026-09-03"),
    (44961, 85, "VACACIONES", "2026-09-03"),
    (43104, 154, "VACACIONES", "2026-08-03"),
    (44769, 154, "VACACIONES", "2026-08-03"),
    (43248, 169, "VACACIONES", "2026-09-07"),
    (43819, 161, "VACACIONES", "2026-09-10"),
    (43886, 178, "VACACIONES", "2026-07-13"),
    (43887, 178, "VACACIONES", "2026-07-13"),
    # Habilitación de operador (resolución 14/09/2023): fecha la de la
    # validez de la categoría B, 12/09/2028 (primera página).
    (43953, 39, "CARNET_GRUISTA", "2028-09-12"),
    (43978, 39, "CARNET_GRUISTA", "2028-09-12"),
    (44301, 39, "CARNET_GRUISTA", "2028-09-12"),
    (44170, 152, "NOMINA", "2017-04-30"),
    (45635, 152, "NOMINA", "2017-04-30"),
    (44171, 152, "NOMINA", "2017-05-01"),
    (45636, 152, "NOMINA", "2017-05-01"),
    (44235, 152, "EPIS", "2019-01-14"),
    (44236, 152, "EPIS", "2016-01-15"),
    (44237, 152, "EPIS", "2016-01-15"),
    (45699, 152, "EPIS", "2016-01-15"),
    (44241, 152, "EPIS", "2017-01-16"),
    (45703, 152, "EPIS", "2017-01-16"),
    (44248, 152, "EPIS", "2015-01-15"),
    (45710, 152, "EPIS", "2015-01-15"),
    (44449, 39, "EPIS", "2018-01-15"),
    (44453, 39, "ENTREGA_DOCUMENTACION_VARIA", "2011-05-16"),
    (45890, 39, "ENTREGA_DOCUMENTACION_VARIA", "2011-05-16"),
    (44637, 40, "EPIS", "2015-04-17"),
    (44922, 85, "EPIS", "2018-01-15"),
    (44928, 85, "EPIS", "2020-04-13"),
    (46338, 85, "EPIS", "2020-04-13"),
    (45087, 156, "EPIS", "2021-01-12"),
    (45139, 3, "CARTA_BAJA_VOLUNTARIA", "2022-04-20"),
    (46538, 3, "CARTA_BAJA_VOLUNTARIA", "2022-04-20"),
    (45294, 3, "EPIS", "2015-01-15"),
    (46685, 3, "EPIS", "2015-01-15"),
    (46924, 158, "CERTIFICADO_BANCARIO", "2019-12-12"),
    (47400, 164, "CERTIF_TRABAJO_COLEGIO", "2024-06-06"),
    (47412, 164, "MOD_145", "2023-08-01"),
    (48075, 250, "MOD_145", "2024-06-21"),
    (47463, 165, "EPIS", "2020-04-13"),
    (48684, 175, "EPIS", "2016-01-15"),
    (48688, 175, "EPIS", "2017-01-16"),
    (48700, 175, "EPIS", "2020-04-13"),
    (48998, 180, "EPIS", "2021-01-12"),
    (49317, 186, "EPIS", "2019-01-14"),
    (49320, 186, "EPIS", "2023-03-06"),
    (49322, 186, "EPIS", "2018-05-07"),
    (49780, 178, "CARTA_BAJA_VOLUNTARIA", "2026-09-02"),
    (49798, 170, "ENTREGA_INFORMACION", "2026-09-03"),
    (49856, 254, "CARNET_CONDUCIR", "2035-01-25"),
    (49858, 254, "TARJETA_CUALIF_CONDUCTOR", "2029-09-27"),
    (51626, 225, "ENTREGA_INFORMACION", "2026-09-25"),
    (51639, 225, "ENTREGA_INFORMACION", "2026-09-25"),
    (51643, 193, "ENTREGA_INFORMACION", ""),
    (52150, 185, "TACOGRAFO", "2030-11-30"),
    (52162, 185, "TACOGRAFO", "2030-11-30"),
    # Segunda revisión: el autorizado es Cruces Heredia (el nombre del
    # archivo decía Cabello Sánchez, la primera página no).
    (51601, 49, "AUTORIZACION_GENERICA", "2026-09-25"),
    # Tercera revisión, tipos nuevos (migración 0179, aprobados).
    (49925, 197, "EXTINCION_CONTRATO", "2026-09-22"),
    (51607, 197, "EXTINCION_CONTRATO", "2026-09-22"),
    (51620, 197, "EXTINCION_CONTRATO", "2026-09-22"),
    (49213, 252, "PRESTACION_NACIMIENTO", "2025-09-29"),
]

# Altas que pasaron desapercibidas: documentos subidos por la vigilancia
# del H28 (no de la carga inicial de julio) de personas sin ficha. Se
# crean con el mismo mecanismo del pipeline
# (`resolve_or_create_person_identity`, carpeta PTE CONTRATACION) y se
# les archiva su documentación. pk -> (tipo, fecha), cualquier carpeta.
NEW_PEOPLE = [
    {
        "dni_hint": "X8250328K", "first_surname_hint": "KOITA",
        "second_surname_hint": "", "given_name_hint": "IBREHIM",
        "documents": [(43214, "NIE", "2035-11-02")],
    },
    {
        # Alta 22/06/2026 en TRANSGRUAL (informe de alta, contrato y DNI
        # leídos en su primera página).
        "dni_hint": "25695295V", "first_surname_hint": "ROSAS",
        "second_surname_hint": "SANCHEZ",
        "given_name_hint": "FRANCISCO JOSE",
        "documents": [
            (37439, "CONTRATO", "2026-06-22"),
            (37446, "ALTA", "2026-06-22"),
            (37445, "IDC", "2026-06-22"),
            (37441, "DNI", "2036-03-06"),
            (37435, "CARNET_CONDUCIR", "2031-07-29"),
            (37436, "TACOGRAFO", "2031-02-06"),
            (37437, "TARJETA_CUALIF_CONDUCTOR", "2031-01-18"),
            (37438, "CERTIFICADO_BANCARIO", "2026-06-22"),
            (37447, "MOD_145", "2026-06-22"),
            (37448, "RECONOCIMIENTO_MEDICO", "2027-06-22"),
            (37440, "FORMACION_OPERADOR_APARATOS_ELEVACION", "2026-06-22"),
            (41189, "FORMACION_PRL_ART_18_19", "2026-06-22"),
            (42832, "FORMACION_PRL_60H", "2026-08-14"),
            (42833, "FORMACION_PRL_60H", "2026-08-14"),
            (37444, "EPIS", "2026-06-18"),
            (41329, "EPIS", "2026-06-18"),
            (44020, "PARTE_BAJA_MEDICA", "2026-09-15"),
        ],
    },
]

# Comprimido Z-100.rar: tres de sus cuatro archivos ya estaban archivados
# por separado; el cuarto (manual de uso de la plataforma, serie
# MULL1513051801) se sube a la ficha de la Z100 y el .rar a la papelera.
RAR_ENTRY = 43190
RAR_MACHINE = 79
RAR_MEMBER_HINT = "Manual"

# pk -> (máquina pk, tipo, fecha).
MACHINE = [
    (49912, 249, "ITV", "2008-10-20"),   # P09 0815CDY
    (49913, 249, "ITV", "2003-01-30"),
    (49914, 249, "ITV", "2018-03-03"),
    (49915, 249, "ITV", "2020-09-25"),
    (49916, 249, "ITV", "2024-02-19"),
    (49917, 249, "ITV", "2025-11-06"),
    (43237, 249, "INFORME_VEHICULO_DGT", "2026-09-04"),
    (43228, 290, "INFORME_VEHICULO_DGT", "2026-09-04"),   # R12 B10513R
    # Venta del Toyota Yaris 1884JBM (máquina 207, TURISMOS).
    (42847, 207, "CONTRATO_COMPRAVENTA", "2026-08-31"),
    (50963, 207, "CONTRATO_COMPRAVENTA", "2026-08-31"),
    (43040, 207, "CAMBIO_TITULARIDAD", "2026-08-31"),
    (43049, 207, "DNI_COMPRADOR", "2026-08-31"),
    (43050, 207, "DNI_COMPRADOR", "2026-08-31"),
    (50965, 207, "DNI_COMPRADOR", "2026-08-31"),
    (50964, 207, "DNI_COMPRADOR", "2026-08-31"),
    (43076, 207, "DNI_COMPRADOR", "2026-08-31"),   # CIF de la compradora
    (50962, 207, "DNI_COMPRADOR", "2026-08-31"),
    (43062, 207, "SOLICITUD_ADMINISTRATIVA", "2026-09-01"),
    (43063, 207, "SOLICITUD_ADMINISTRATIVA", "2026-09-01"),
    (50968, 207, "SOLICITUD_ADMINISTRATIVA", "2026-09-01"),
    # Segunda revisión: certificado del taller de la Sprinter 4542KGD
    # (máquina 311) y transporte de la Liebherr LTF1060 (A68, 572).
    (45493, 311, "REFORMA_VEHICULO", "2026-09-01"),
    (43997, 311, "REFORMA_VEHICULO", "2026-09-01"),
    (49929, 572, "ALBARAN_ENTREGA", "2026-09-21"),
    (49930, 572, "ALBARAN_ENTREGA", "2026-09-21"),
    (51885, 572, "ALBARAN_ENTREGA", "2026-09-21"),
]


def _live_anywhere(pk):
    return DocumentIndexEntry.objects.filter(
        pk=pk, entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).first()


def _live(pk, parent_path):
    return DocumentIndexEntry.objects.filter(
        pk=pk, bucket=PRIMARY_BUCKET,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
        parent_path=parent_path,
    ).first()


class Command(BaseCommand):
    help = (
        "S127: aplica la revisión de NO CONFORMES/CLASIFICACION. Sin "
        "--apply solo informa."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def _say(self, text):
        self.stdout.write(text)
        self.stdout.flush()

    def handle(self, *args, **options):
        apply = options["apply"]
        self._say("# [S127] Revisión de NO CONFORMES -- %s" % (
            "APLICANDO" if apply else "MODO PRUEBA (sin --apply)"))
        counts = {"empresa": 0, "ficha": 0, "papelera": 0,
                  "duplicado": 0, "saltado": 0}

        # 1) Movimientos de carpeta.
        self._say("1. A carpeta:")
        groups = {}
        for source, mapping in ((SOURCE, MOVES), (COMPANY, COMPANY_TIDY)):
            for pk, destination in mapping.items():
                entry = _live(pk, source)
                if entry is None:
                    counts["saltado"] += 1
                    self._say("   - pk=%s: ya no está en %s." % (pk, source))
                    continue
                self._say("   - pk=%s %s -> %s" % (
                    pk, entry.name, destination))
                groups.setdefault(destination, []).append(entry)
                counts["empresa"] += 1
        if apply:
            for destination, entries in groups.items():
                move_entries(entries, destination)

        # 2) Papelera pedida.
        self._say("2. A la papelera:")
        for pk in sorted(TRASH):
            entry = _live(pk, SOURCE)
            if entry is None:
                counts["saltado"] += 1
                continue
            self._say("   - pk=%s %s" % (pk, entry.name))
            counts["papelera"] += 1
            if apply and not trash_dossier_entry(entry):
                self._say("     [ERROR] no se pudo mandar a la papelera.")

        # 3) Fichas de persona y de máquina.
        self._say("3. A su ficha:")
        people = {p.pk: p for p in PersonIdentity.objects.filter(
            pk__in={row[1] for row in PERSONAL})}
        assets = {m.pk: m for m in MachineAsset.objects.filter(
            pk__in={row[1] for row in MACHINE})}
        for rows, subjects in ((PERSONAL, people), (MACHINE, assets)):
            for pk, subject_pk, type_code, date_hint in rows:
                entry = _live(pk, SOURCE)
                if entry is None:
                    counts["saltado"] += 1
                    continue
                subject = subjects.get(subject_pk)
                if subject is None:
                    counts["saltado"] += 1
                    self._say("   - pk=%s [SALTADO] dueño %s no existe." % (
                        pk, subject_pk))
                    continue
                # Copia de algo ya archivado (incluido lo archivado
                # unas líneas antes en esta misma ejecución).
                if apply and resolve_duplicate_of_filed_document(entry):
                    counts["duplicado"] += 1
                    self._say("   - pk=%s %s: copia exacta de un archivado "
                              "-> papelera." % (pk, entry.name))
                    trash_dossier_entry(entry)
                    continue
                outcome = file_entry_manually(
                    entry, subject, type_code, date_hint,
                    apply_changes=apply,
                )
                if outcome["reason"]:
                    counts["saltado"] += 1
                    self._say("   - pk=%s %s [SALTADO] %s" % (
                        pk, entry.name, outcome["reason"]))
                    continue
                counts["ficha"] += 1
                self._say("   - pk=%s %s -> %s/%s" % (
                    pk, entry.name, outcome["new_parent_path"],
                    outcome["new_name"]))

        # 4) Altas desapercibidas.
        self._say("4. Altas que pasaron desapercibidas:")
        for person in NEW_PEOPLE:
            label = "%s %s, %s (%s)" % (
                person["first_surname_hint"], person["second_surname_hint"],
                person["given_name_hint"], person["dni_hint"])
            existing = PersonIdentity.objects.filter(
                dni=person["dni_hint"]).first()
            if existing is not None:
                identity = existing
                self._say("   - %s: ya existe (pk=%s)." % (label, existing.pk))
            elif apply:
                first_live = _live_anywhere(person["documents"][0][0])
                hints = {k: v for k, v in person.items() if k != "documents"}
                identity = resolve_or_create_person_identity(
                    hints, first_live)
                if identity is None:
                    self._say("   - %s [SALTADO] %s" % (
                        label, hints.get("person_identity_note", "")))
                    counts["saltado"] += 1
                    continue
                self._say("   - %s: creada (pk=%s) en %s." % (
                    label, identity.pk, identity.folder_path))
            else:
                identity = None
                self._say("   - %s: se crearía en PTE CONTRATACION." % label)
            for pk, type_code, date_hint in person["documents"]:
                entry = _live_anywhere(pk)
                if entry is None:
                    counts["saltado"] += 1
                    self._say("     - pk=%s: no está vivo." % pk)
                    continue
                if identity is None:
                    self._say("     - pk=%s %s -> %s (%s)" % (
                        pk, entry.name, type_code, date_hint))
                    continue
                if apply and resolve_duplicate_of_filed_document(entry):
                    counts["duplicado"] += 1
                    self._say("     - pk=%s %s: copia exacta -> papelera."
                              % (pk, entry.name))
                    trash_dossier_entry(entry)
                    continue
                outcome = file_entry_manually(
                    entry, identity, type_code, date_hint,
                    apply_changes=apply,
                )
                if outcome["reason"]:
                    counts["saltado"] += 1
                    self._say("     - pk=%s [SALTADO] %s" % (
                        pk, outcome["reason"]))
                    continue
                counts["ficha"] += 1
                self._say("     - pk=%s -> %s/%s" % (
                    pk, outcome["new_parent_path"], outcome["new_name"]))

        # 5) Comprimido Z-100.rar.
        self._say("5. Comprimido Z-100.rar:")
        rar = _live(RAR_ENTRY, SOURCE)
        if rar is None:
            self._say("   - ya no está en %s." % SOURCE)
        else:
            content = download_bytes(rar.bucket, rar.blob_name)
            members = archive_service.list_entries(content, "rar") or []
            manual = next((
                m["path"] for m in members
                if RAR_MEMBER_HINT.lower() in m["path"].lower()
            ), None)
            self._say("   - contenido: %s" % ", ".join(
                m["path"] for m in members))
            if manual is None:
                counts["saltado"] += 1
                self._say("   [SALTADO] no aparece el manual.")
            elif apply:
                data = archive_service.extract_entry(content, "rar", manual)
                asset = MachineAsset.objects.get(pk=RAR_MACHINE)
                uploaded = upload_subject_document(
                    subject=asset,
                    domain_content_type=ContentType.objects.get_for_model(
                        MachineAsset),
                    document_type=DocumentTypeCatalog.objects.get(
                        code="MANUAL_USO"),
                    data=data, original_filename=manual.rsplit("/", 1)[-1],
                    typed_date=None, subject_label=asset.code,
                )
                trash_dossier_entry(rar)
                counts["ficha"] += 1
                counts["papelera"] += 1
                self._say("   - %s -> %s/%s; .rar a la papelera." % (
                    manual, uploaded["entry"].parent_path,
                    uploaded["entry"].name))
            else:
                self._say("   - subiría %s a la ficha de la máquina %s y "
                          "mandaría el .rar a la papelera." % (
                              manual, RAR_MACHINE))

        remaining = DocumentIndexEntry.objects.filter(
            bucket=PRIMARY_BUCKET, entry_kind=DocumentIndexEntry.KIND_FILE,
            deleted_at__isnull=True, purged_at__isnull=True,
            parent_path=SOURCE,
        ).count()
        self._say(
            "# [S127] Fin. Carpeta: %(empresa)d. Ficha: %(ficha)d. "
            "Papelera: %(papelera)d. Duplicados: %(duplicado)d. "
            "Saltados: %(saltado)d." % counts
            + " Quedan en %s: %d%s." % (
                SOURCE, remaining,
                "" if apply else " (antes de aplicar)")
        )

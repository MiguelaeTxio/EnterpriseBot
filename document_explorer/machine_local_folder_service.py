# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/machine_local_folder_service.py
"""
H31 (S148). A machine's folder in the local OneDrive tree
(DOC. MAQUINAS), kept by the H28 agent, the same way as the workers'
folders (local_download_service).

---

H31 (S148). La carpeta de una máquina en el árbol local de OneDrive
(DOC. MAQUINAS), que mantiene el agente H28 igual que las de los
trabajadores (local_download_service). Miguel Ángel: "que no tengan
que estar pendiente a las carpetas, sino que automáticamente se
actualicen [...] con los mismos formatos en los que están trabajando".

Reglas (decididas con Miguel Ángel en S148):
- La carpeta va según la letra del código: A grúas móviles, B camiones
  brazo, Z plataformas, P cabezas tractoras, R remolques, G góndolas,
  T carretillas; X y turismos, vehículos de empresa; el resto, VARIOS.
  Las dependencias (y el centro de gasto PERSONAL) no tienen carpeta.
- De baja, a la carpeta de bajas de su familia: las que ya tenéis
  (VEHICULOS BAJA, VEHICULOS DE BAJA, BAJAS, BAJA, BAJA DEFINITIVA) y
  BAJAS en remolques, góndolas, carretillas y VARIOS.
- Una máquina sin carpeta: "B-12 8008-BRB (TR)" (código con guion,
  matrícula, empresa); un turismo, "DOCUMENT {matrícula}". Una que ya
  la tiene conserva su nombre.
- La carpeta actual es la de su última descarga o, si no tiene, la
  carpeta local de la que se subieron sus documentos (el nombre del
  objeto en el cubo es su ruta en local), reconocida por llevar el
  código o la matrícula de la máquina.
- Como en Personal, en local no se renombra nada: el agente mueve la
  carpeta entera si cambia de sitio y baja lo subido desde el panel
  (con su nombre canónico) que no esté.
"""
import collections
import re
import unicodedata

from django.contrib.contenttypes.models import ContentType

from .local_download_service import obsolete_moves
from .models import DocumentIndexEntry, LocalDownloadJob

BUCKET = "cgs_grupo_alvarez"
LOCAL_ROOT = "DOC. MAQUINAS"
# Lo subido desde el panel vive solo en el cubo (estructura virtual).
PANEL_PREFIXES = (LOCAL_ROOT + "/ACTIVAS/", LOCAL_ROOT + "/INACTIVAS/")
NO_LOCAL_FAMILIES = ("DEPENDENCIAS", "PERSONAL")
TURISMOS = "TURISMOS"
VARIOS = "VARIOS"
_RG = "REMOLQUES Y GONDOLAS (R y G)"
# Clave -> (carpeta de activas, carpeta de bajas), dentro de LOCAL_ROOT.
LOCAL_CONTAINERS = {
    "A": ("GRUAS MOVILES (A)", "GRUAS MOVILES (A)/VEHICULOS BAJA"),
    "B": ("CAMIONES BRAZO (B)", "CAMIONES BRAZO (B)/VEHICULOS DE BAJA"),
    "Z": ("PLATAFORMAS (Z)", "PLATAFORMAS (Z)/BAJAS"),
    "P": ("CABEZAS TRACTORAS (P)", "CABEZAS TRACTORAS (P)/BAJA"),
    "R": (_RG + "/REMOLQUES", _RG + "/REMOLQUES/BAJAS"),
    "G": (_RG + "/GONDOLAS", _RG + "/GONDOLAS/BAJAS"),
    "T": ("CARRETILLAS (T)", "CARRETILLAS (T)/BAJAS"),
    TURISMOS: ("VEHICULOS DE EMPRESA",
               "VEHICULOS DE EMPRESA/BAJA DEFINITIVA"),
    VARIOS: ("VARIOS", "VARIOS/BAJAS"),
}
# Código de empresa de la carpeta (como las que ya hay: GR, TR, GL, AGG).
COMPANY_CODES = {
    "GRA": "GR", "GRB": "GR", "GRH": "GR",
    "TRA": "TR", "TRB": "TR",
    "GLA": "GL",
    "GRG": "AGG",
}
_CODE = re.compile(r"^([A-Z]+)-?(\d+)$")


def _plain(text):
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(
        c for c in text if not unicodedata.combining(c)).upper().strip()


def _compact(text):
    return re.sub(r"[^A-Z0-9]", "", _plain(text))


def has_local_folder(machine):
    """
    False for dependencies and the PERSONAL cost centre.

    ---

    False para las dependencias y el centro de gasto PERSONAL, que no
    tienen carpeta local.
    """
    return _plain(machine.family) not in NO_LOCAL_FAMILIES


def _container_key(machine):
    code = _plain(machine.code)
    if _plain(machine.family) == TURISMOS or code.startswith("X"):
        return TURISMOS
    letter = code[:1]
    return letter if letter in LOCAL_CONTAINERS else VARIOS


def _code_pattern(machine):
    """
    Regex that finds the machine code inside a folder name ("A-29",
    "A29", "T 05" all match code A29 / T05, never A-290).

    ---

    Expresión que reconoce el código de la máquina dentro del nombre de
    una carpeta, con o sin guion ("A-29", "A29"), sin confundir A-29 con
    A-290.
    """
    match = _CODE.match(_plain(machine.code))
    if not match:
        return None
    letters, digits = match.groups()
    return re.compile(r"(?<![A-Z0-9])%s[-\s]?0*%d(?!\d)" % (
        re.escape(letters), int(digits)))


def machine_folder_of(machine, path):
    """
    The local folder of this machine a path is in, or None.

    ---

    La carpeta de la máquina (la primera, por debajo de la familia, que
    lleve su código o su matrícula) en la que está una ruta local, o
    None. Nunca una carpeta de primer nivel (una familia).
    """
    parts = path.split("/")
    if len(parts) < 4 or parts[0] != LOCAL_ROOT:
        return None
    if path.startswith(PANEL_PREFIXES):
        return None
    pattern = _code_pattern(machine)
    plate = _compact(machine.plate)
    for depth in range(2, len(parts) - 1):
        segment = _plain(parts[depth])
        if (pattern is not None and pattern.search(segment)) or (
                len(plate) >= 5 and plate in _compact(segment)):
            return "/".join(parts[:depth + 1])
    return None


def _machine_entries(machine):
    from fleet.models import MachineAsset

    return DocumentIndexEntry.objects.filter(
        bucket=BUCKET,
        domain_content_type=ContentType.objects.get_for_model(MachineAsset),
        domain_object_id=machine.pk,
        entry_kind=DocumentIndexEntry.KIND_FILE,
        deleted_at__isnull=True, purged_at__isnull=True,
    ).order_by("pk")


def current_local_folder(machine):
    """
    Where the machine's folder is now in the local tree, or "".

    ---

    Dónde está ahora la carpeta de la máquina en local: la de su última
    descarga o, si no tiene, la carpeta de la que se subieron más
    documentos suyos; "" si no tiene ninguna.
    """
    last = LocalDownloadJob.objects.filter(machine=machine).exclude(
        folder="").order_by("-created_at", "-pk").first()
    if last is not None:
        return last.folder
    counts = collections.Counter(
        folder for folder in (
            machine_folder_of(machine, blob) for blob in _machine_entries(
                machine).values_list("blob_name", flat=True)
        ) if folder
    )
    return counts.most_common(1)[0][0] if counts else ""


def new_folder_name(machine):
    """
    Folder name for a machine without a local folder yet.

    ---

    Nombre de la carpeta de una máquina que todavía no la tiene:
    "B-12 8008-BRB (TR)"; un turismo, "DOCUMENT {matrícula}".
    """
    plate = _plain(machine.plate)
    if _container_key(machine) == TURISMOS:
        return ("DOCUMENT %s" % (plate or _plain(machine.code))).strip()
    code = _plain(machine.code)
    match = _CODE.match(code)
    if match:
        code = "%s-%s" % match.groups()
    company = COMPANY_CODES.get(_plain(machine.company_code), "")
    name = " ".join(part for part in (code, plate) if part)
    return name + (" (%s)" % company if company else "")


def target_local_folder(machine, current=""):
    """
    Where the machine's folder must be (its family, active or not).

    ---

    Dónde tiene que estar la carpeta: la de su familia, de activas o de
    bajas, con el nombre que ya tenga.
    """
    active, inactive = LOCAL_CONTAINERS[_container_key(machine)]
    container = active if machine.is_active else inactive
    name = current.rsplit("/", 1)[-1] if current else new_folder_name(
        machine)
    return "%s/%s/%s" % (LOCAL_ROOT, container, name)


def create_for_machine(machine, requested_by=None, previous=None,
                       always=False, obsolete=()):
    """
    Create the job that leaves the machine's local folder in place.

    ---

    Crea el trabajo que deja la carpeta local de la máquina donde le
    toca. `previous` es su carpeta antes del cambio (current_local_folder
    tomado antes de cambiarla); sin él, la de ahora. Archivos: lo
    subido desde el panel, a la raíz de su carpeta. Con `always` (alta)
    se crea aunque no haya nada que bajar: el agente crea la carpeta.
    `obsolete`: pares (blob_name, name) de documentos sustituidos, que
    pasan a OBSOLETOS en local.
    None si la máquina no tiene carpeta local o no hay nada que hacer.
    """
    if not has_local_folder(machine):
        return None
    current = previous if previous is not None else current_local_folder(
        machine)
    target = target_local_folder(machine, current)
    files = [
        {"blob": blob, "path": "%s/%s" % (target, name)}
        for blob, name in _machine_entries(machine).values_list(
            "blob_name", "name")
        if blob.startswith(PANEL_PREFIXES)
    ]
    if not files and not current and not always:
        return None
    return LocalDownloadJob.objects.create(
        machine=machine, requested_by=requested_by, files=files,
        folder=target, previous_folder=current,
        obsolete_files=obsolete_moves(
            obsolete, current, target, PANEL_PREFIXES),
    )


def queue_for_entry(entry, requested_by=None):
    """
    After a document enters from the panel, bring it to the local
    folder of its person or machine (on commit).

    ---

    Tras entrar un documento desde el panel (ficha, avisos, bandeja,
    solicitudes...), lo baja a la carpeta local de su persona o máquina,
    al confirmar la transacción. Miguel Ángel (S148): "si lo subimos a
    través de la plataforma con una actualización de documento, ¿nos
    hace la vuelta a Microsoft 365?". Nunca rompe la subida.
    """
    from django.db import transaction

    from fleet.models import MachineAsset

    from .local_download_service import PANEL_PREFIXES as PERSON_PREFIXES
    from .local_download_service import create_for_person
    from .models import PersonIdentity

    if entry.domain_content_type_id and (
            entry.domain_content_type.model == "companyfiscalprofile"):
        # S156: lo de una empresa del grupo baja a la carpeta local de
        # su clase (company_local_folder_service).
        from .company_local_folder_service import create_for_company_entry

        def run_company():
            try:
                create_for_company_entry(entry, requested_by=requested_by)
            except Exception:  # noqa: BLE001 -- nunca rompe la subida
                import logging
                logging.getLogger(__name__).exception(
                    "Descarga a local tras subir %s: no se pudo crear el "
                    "trabajo.", entry.pk)

        transaction.on_commit(run_company)
        return
    if not entry.blob_name.startswith(PANEL_PREFIXES + PERSON_PREFIXES):
        return
    # S149: un documento confidencial (nómina, S147) no baja nunca a
    # local: en el cubo está cifrado y solo lo abren el trabajador y
    # quien lo envió.
    if entry.is_confidential:
        return
    model = entry.domain_content_type.model_class() if (
        entry.domain_content_type_id) else None
    object_id = entry.domain_object_id

    def run():
        import logging

        from document_management.models import DocumentSubstitutionLog

        try:
            # S148 (Miguel Ángel): "deberíamos de pasar automáticamente
            # el documento antiguo a obsoletos [...] nuevo DNI lo subes y
            # te olvidas": lo que esta subida ha sustituido.
            superseded = DocumentSubstitutionLog.objects.filter(
                superseding_content_type=ContentType.objects.get_for_model(
                    DocumentIndexEntry),
                superseding_object_id=entry.pk,
            ).values_list("superseded_object_id", flat=True)
            obsolete = list(DocumentIndexEntry.objects.filter(
                pk__in=list(superseded)).values_list("blob_name", "name"))
            if model is PersonIdentity:
                person = PersonIdentity.objects.filter(pk=object_id).first()
                if person is not None:
                    create_for_person(person, requested_by=requested_by,
                                      obsolete=obsolete)
            elif model is MachineAsset:
                machine = MachineAsset.objects.filter(pk=object_id).first()
                if machine is not None:
                    create_for_machine(machine, requested_by=requested_by,
                                       obsolete=obsolete)
        except Exception:  # noqa: BLE001 -- nunca rompe la subida
            logging.getLogger(__name__).exception(
                "Descarga a local tras subir %s: no se pudo crear el "
                "trabajo.", entry.pk)

    transaction.on_commit(run)


def follow_change(machine, previous, requested_by=None):
    """
    After a change of state or data, move the local folder if its
    place changed.

    ---

    Tras dar de baja, reactivar o cambiar los datos de una máquina:
    crea el trabajo solo si su carpeta local tiene que cambiar de sitio
    (`previous` es la de antes, current_local_folder tomado antes del
    cambio). Si no tiene carpeta conocida, no hace nada (se crea en el
    alta o al subirle un documento desde el panel).
    """
    if not has_local_folder(machine) or not previous:
        return None
    if target_local_folder(machine, previous) == previous:
        return None
    return create_for_machine(
        machine, requested_by=requested_by, previous=previous)

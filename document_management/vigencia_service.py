# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_management/vigencia_service.py
"""
Servicio de vigencia y sustitucion de documentos (Hito 26, anexo
seccion 2.4). Consumido por H23/machine_documents desde S023, y desde
S024 tambien por panel/views_documentation.py para personal_documents
(H25) -- ya no bloqueado por el modelo de datos de H25, cerrado en
S024 (ver commit 5640da6).

Implementa el criterio de vigencia cerrado en H23 S021 ("Todos los
documentos seran vigentes cuando la fecha de caducidad no se haya
alcanzado o fecha de emision o el periodo de referencia sean mas
modernos"), interpretado y confirmado con Miguel Angel en S023:

- Documentos CON expiry_date (certificados OCA, tarjeta ITV, recibos
  de seguro...): vigentes mientras esa fecha no haya pasado. No se
  comparan entre si -- varios documentos del mismo tipo pueden ser
  vigentes a la vez si representan periodos distintos (ej. recibos de
  seguro trimestrales, ver H23 anexo seccion 3.1 sobre period_start/
  period_end).
- Documentos SIN expiry_date pero con issue_date/periodo (ficha
  tecnica, declaracion CE...): como no caducan por si solos, el mas
  reciente de su mismo tipo es el vigente, los anteriores quedan
  archivados. issue_date ya se extrae con Gemini Vision leyendo el
  propio documento (sellos, firmas, fechas de revision reales -- ver
  machine_documents.document_classification_service), nunca de
  metadatos de archivo.
- Documentos SIN NINGUNA fecha (ni expiry_date ni issue_date): el mas
  recientemente indexado (`DocumentSnapshot.indexed_at`, si el
  llamador lo rellena) es el vigente, los anteriores quedan
  archivados -- mismo criterio "el mas reciente gana" que el caso de
  arriba, aplicado por fecha de subida en vez de por fecha del propio
  documento. Anadido S102 tras incidente real: sin este criterio,
  cualquier tipo con `tracks_expiry=True` pero sin fecha real
  extraible se quedaba "vigente por defecto" sin limite, sin importar
  cuantas veces se resubiera.

Este modulo trabaja sobre datos genericos (fechas + identificador
opaco) -- NUNCA importa MachineDocument ni el futuro modelo de H25,
para que ningun dominio duplique esta logica (mismo principio DRY que
origino el hito, ver anexo H26 seccion 1).

---

Document currency and substitution service (Milestone 26, annex
section 2.4). Consumed today only by H23/machine_documents -- personnel
(H25) remains pending until its data model is closed (Miguel Angel's
explicit decision, S023).
"""
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class DocumentSnapshot:
    """
    Datos minimos de un documento (existente o entrante) necesarios
    para evaluar vigencia/sustitucion. `identifier` es opaco para este
    modulo -- el llamador lo usa para saber a cual de sus propios
    registros de dominio corresponde cada resultado.

    `indexed_at` (H31, S102) es opcional -- solo lo usa el desempate de
    documentos SIN NINGUNA fecha (ver `is_current()`). Un llamador que
    no lo rellene mantiene exactamente el comportamiento anterior
    (nunca se archiva a ciegas sin datos), sin ningun efecto sobre
    quien no lo pase -- ver incidente real S102 que motivo este campo.
    ---
    Minimal document data (existing or incoming) needed to evaluate
    currency/substitution. `identifier` is opaque to this module -- the
    caller uses it to know which of its own domain records each result
    corresponds to.
    """
    identifier: object
    expiry_date: date | None = None
    issue_date: date | None = None
    indexed_at: datetime | None = None


def is_current(
    candidate: DocumentSnapshot,
    siblings: list[DocumentSnapshot],
    today: date | None = None,
) -> bool:
    """
    Determina si `candidate` es vigente frente al resto de documentos
    del mismo tipo (`siblings`, sin incluir al propio candidate; el
    llamador ya debe haber filtrado por misma maquina/trabajador +
    mismo document_type).
    ---
    Determines whether `candidate` is current relative to the rest of
    the documents of the same type (`siblings`, excluding candidate
    itself; the caller must already have filtered by same machine/
    worker + same document_type).
    """
    reference_today = today or date.today()

    if candidate.expiry_date is not None:
        return candidate.expiry_date >= reference_today

    if candidate.issue_date is not None:
        sibling_issue_dates = [
            s.issue_date for s in siblings
            if s.expiry_date is None and s.issue_date is not None
        ]
        if not sibling_issue_dates:
            return True
        return candidate.issue_date >= max(sibling_issue_dates)

    # Ningun dato real (ni caducidad ni emision) en el candidato.
    # INCIDENTE REAL S102: esta rama devolvia True sin mas ("no hay
    # base para archivar"), lo que dejaba vigentes a la vez tantos
    # documentos del mismo tipo como se subieran (4 subidas seguidas
    # de un mismo CONTRATO sin fecha, ninguna marcada obsoleta nunca).
    # Miguel Angel, verbatim: "los documentos deben quedar siempre
    # como historicos cuando dejan de ser los vigentes". Corregido:
    # entre varios documentos igualmente ciegos (sin ninguna fecha),
    # el mas recientemente indexado prevalece; los demas se archivan.
    # Si el propio llamador no rellena `indexed_at` (comportamiento
    # por defecto de siempre, ver `DocumentSnapshot`), esta rama no
    # cambia de comportamiento -- se sigue considerando vigente por
    # defecto, nunca se archiva a ciegas sin ningun dato temporal.
    dateless_siblings = [
        s for s in siblings
        if s.expiry_date is None and s.issue_date is None
    ]
    if not dateless_siblings or candidate.indexed_at is None:
        return True
    sibling_indexed_ats = [
        s.indexed_at for s in dateless_siblings if s.indexed_at is not None
    ]
    if not sibling_indexed_ats:
        return True
    return candidate.indexed_at >= max(sibling_indexed_ats)


@dataclass(frozen=True)
class SubstitutionResult:
    """
    Resultado de comparar un documento entrante contra los existentes
    del mismo tipo. Diseño original del anexo H26 seccion 2.4 (dialogo
    interactivo que preguntaba al usuario), corregido en S025: la
    sustitucion se aplica en SILENCIO, sin dialogo -- el llamador
    (hoy machine_documents/tasks.py) usa este resultado para archivar/
    registrar directamente, nunca para mostrar una pregunta al
    usuario. Este modulo sigue sin decidir nada por si mismo ni
    persistir nada -- solo informa; quien llama decide que hacer con
    el resultado.
    """
    has_existing_of_same_type: bool
    incoming_should_prevail: bool
    existing_to_archive: list = field(default_factory=list)
    reasoning: str = ""


def evaluate_substitution(
    incoming: DocumentSnapshot,
    existing_same_type: list[DocumentSnapshot],
    today: date | None = None,
) -> SubstitutionResult:
    """
    Compara un documento entrante contra los documentos existentes del
    mismo tipo (misma maquina + mismo document_type, ya resuelto por
    el llamador -- este modulo no consulta ninguna BD) y devuelve el
    resultado de la comparacion. Diseño original del anexo H26 seccion
    2.4: la interfaz mostraba un dialogo con dos acciones (archivar el
    obsoleto / revertir la subida entrante). Corregido en S025 -- el
    llamador (hoy machine_documents/tasks.py, Step 2bis) usa este
    resultado para archivar y registrar en DocumentSubstitutionLog
    directamente, en silencio, sin mostrar ningun dialogo. Este modulo
    sigue sin archivar ni persistir nada -- solo informa.
    """
    if not existing_same_type:
        return SubstitutionResult(
            has_existing_of_same_type=False,
            incoming_should_prevail=True,
            existing_to_archive=[],
            reasoning=(
                "No hay documento previo del mismo tipo -- se persiste "
                "directamente, sin mostrar el dialogo."
            ),
        )

    reference_today = today or date.today()
    all_docs = existing_same_type + [incoming]
    incoming_should_prevail = is_current(
        incoming, existing_same_type, reference_today,
    )

    if incoming_should_prevail:
        existing_to_archive = [
            existing.identifier
            for existing in existing_same_type
            if not is_current(
                existing,
                [d for d in all_docs if d is not existing],
                reference_today,
            )
        ]
        reasoning = (
            "El documento entrante es igual o mas reciente que el/los "
            "existente(s) del mismo tipo -- debe prevalecer como vigente."
        )
    else:
        existing_to_archive = []
        reasoning = (
            "El documento entrante es mas antiguo que el vigente actual "
            "-- no deberia prevalecer; ofrecer revertir la subida en el "
            "dialogo."
        )

    return SubstitutionResult(
        has_existing_of_same_type=True,
        incoming_should_prevail=incoming_should_prevail,
        existing_to_archive=existing_to_archive,
        reasoning=reasoning,
    )

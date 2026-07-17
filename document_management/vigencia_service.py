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
from datetime import date


@dataclass(frozen=True)
class DocumentSnapshot:
    """
    Datos minimos de un documento (existente o entrante) necesarios
    para evaluar vigencia/sustitucion. `identifier` es opaco para este
    modulo -- el llamador lo usa para saber a cual de sus propios
    registros de dominio corresponde cada resultado.
    ---
    Minimal document data (existing or incoming) needed to evaluate
    currency/substitution. `identifier` is opaque to this module -- the
    caller uses it to know which of its own domain records each result
    corresponds to.
    """
    identifier: object
    expiry_date: date | None = None
    issue_date: date | None = None


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

    if candidate.issue_date is None:
        # Sin ninguna fecha -- no hay base para archivar; se considera
        # vigente por defecto (nunca se archiva a ciegas sin datos).
        return True

    sibling_issue_dates = [
        s.issue_date for s in siblings
        if s.expiry_date is None and s.issue_date is not None
    ]
    if not sibling_issue_dates:
        return True
    return candidate.issue_date >= max(sibling_issue_dates)


@dataclass(frozen=True)
class SubstitutionResult:
    """
    Resultado de comparar un documento entrante contra los existentes
    del mismo tipo, para el dialogo de sustitucion (anexo H26 seccion
    2.4). Nunca decide por si mismo archivar/revertir -- solo informa;
    la decision final es siempre del usuario en el dialogo.
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
    resultado de la comparacion para que la interfaz de H23 muestre el
    dialogo con las dos acciones (archivar el obsoleto / revertir la
    subida entrante). Flujo tal cual lo describio Miguel Angel, anexo
    H26 seccion 2.4 -- este modulo NUNCA archiva ni persiste nada.
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

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
  de seguro...): vigentes mientras esa fecha no haya pasado. **Corregido
  en H35 (S108):** entre varios documentos del mismo tipo+persona/
  maquina con expiry_date todavia valida, solo el de fecha mas lejana
  es el vigente -- ya no coexisten varios a la vez sin limite (ver
  `is_current()` para el desempate real en fechas empatadas). La nota
  original de este docstring (H26/S023) decia que "no se comparan entre
  si" citando recibos de seguro trimestrales como ejemplo de varios
  vigentes a la vez -- **superada** por el campo `is_cumulative` de
  `DocumentTypeCatalog` (H35, S107): todo tipo con `tracks_expiry=True`
  hoy en el catalogo (maquina o personal) tiene `is_cumulative=False`,
  es decir, el diseño real vigente es "solo uno a la vez" en ambos
  dominios. Un tipo que de verdad necesite coexistencia real (varios
  periodos legitimamente vigentes al mismo tiempo) debe marcarse
  `is_cumulative=True` en el catalogo -- este modulo no distingue por
  si mismo `is_cumulative`, es responsabilidad del llamador filtrar
  antes de invocar `is_current()`/`evaluate_substitution()` (mismo
  patron ya usado por `backfill_obsolete_duplicates` en el dominio
  personal).
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
        if candidate.expiry_date < reference_today:
            return False
        # H35 (S108), incidente real: esta rama solo comparaba contra
        # `reference_today`, nunca contra los hermanos -- dos
        # documentos del mismo tipo+persona/maquina con expiry_date
        # futura quedaban vigentes A LA VEZ sin limite (12 grupos reales
        # confirmados: CONTRATO, CARNET_GRUISTA, TARJETA_CUALIF_
        # CONDUCTOR, CARNET_CONDUCIR, PARTE_BAJA_MEDICA,
        # RECONOCIMIENTO_MEDICO). Corregido: entre los hermanos cuya
        # propia expiry_date todavia no ha pasado, gana el de fecha mas
        # lejana; un hermano ya caducado nunca compite (esta obsoleto
        # el solo, por su propia fecha). Mismo criterio de "hermano
        # valido" tanto si tiene expiry_date futura como issue_date sin
        # expiry_date (ese tipo no caduca por si solo -- ver rama de
        # abajo -- asi que siempre cuenta como competencia valida).
        valid_dated_siblings = [
            s for s in siblings
            if (s.expiry_date is not None and s.expiry_date >= reference_today)
            or (s.expiry_date is None and s.issue_date is not None)
        ]
        if not valid_dated_siblings:
            return True
        sibling_expiries = [
            s.expiry_date for s in valid_dated_siblings
            if s.expiry_date is not None
        ]
        # Un hermano sin expiry_date pero con issue_date (tipo que no
        # caduca por si solo) siempre es mas "actual" que cualquier
        # documento con expiry_date propia -- mismo principio que la
        # rama de abajo, donde ese tipo de hermano define el vigente
        # por su propio issue_date, nunca por comparacion de caducidad.
        if len(sibling_expiries) < len(valid_dated_siblings):
            return False
        max_sibling_expiry = max(sibling_expiries)
        if candidate.expiry_date > max_sibling_expiry:
            return True
        if candidate.expiry_date < max_sibling_expiry:
            return False
        # Empate exacto de expiry_date -- mismo desempate que el caso
        # "sin fecha ninguna" de mas abajo: el mas recientemente
        # indexado prevalece. Si no hay indexed_at (comportamiento por
        # defecto de siempre), se mantiene vigente -- nunca se archiva
        # a ciegas sin dato temporal para desempatar.
        if candidate.indexed_at is None:
            return True
        tied_siblings_indexed_ats = [
            s.indexed_at for s in valid_dated_siblings
            if s.expiry_date == candidate.expiry_date and s.indexed_at is not None
        ]
        if not tied_siblings_indexed_ats:
            return True
        return candidate.indexed_at >= max(tied_siblings_indexed_ats)

    if candidate.issue_date is not None:
        sibling_issue_docs = [
            s for s in siblings
            if s.expiry_date is None and s.issue_date is not None
        ]
        if not sibling_issue_docs:
            return True
        max_sibling_issue = max(s.issue_date for s in sibling_issue_docs)
        if candidate.issue_date > max_sibling_issue:
            return True
        if candidate.issue_date < max_sibling_issue:
            return False
        # H35 (S108), segundo incidente real distinto del de arriba:
        # esta rama nunca desempataba en absoluto -- con `>=` contra
        # el maximo, TODOS los hermanos con exactamente la misma
        # issue_date que el maximo (incluido el propio candidato)
        # devolvian True a la vez. Confirmado con datos reales
        # (CONTRATO/PARTE_BAJA_MEDICA/SEGURO con issue_date identica
        # entre hermanos, indexed_at casi identico -- duplicados
        # reales de la migracion historica). Mismo desempate que las
        # otras dos ramas: el mas recientemente indexado prevalece: si
        # no hay indexed_at, se mantiene vigente (nunca se archiva a
        # ciegas sin dato para desempatar).
        if candidate.indexed_at is None:
            return True
        tied_siblings_indexed_ats = [
            s.indexed_at for s in sibling_issue_docs
            if s.issue_date == candidate.issue_date and s.indexed_at is not None
        ]
        if not tied_siblings_indexed_ats:
            return True
        return candidate.indexed_at >= max(tied_siblings_indexed_ats)

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
    #
    # SEGUNDO INCIDENTE REAL (H31 S103), distinto del de arriba: el
    # desempate de mas arriba solo comparaba el candidato ciego contra
    # OTROS hermanos igual de ciegos -- si el unico hermano SI tenia
    # fecha real, no habia "hermano ciego" contra el que comparar, y
    # el candidato se colaba como vigente igualmente, en paralelo al
    # que si tenia fecha (ficha real: tipo NIE de una persona con dos
    # documentos vigentes a la vez, uno con expiry_date=2030-12-04 y
    # otro sin ninguna fecha). Confirmado por Miguel Angel: un
    # documento sin ninguna fecha NUNCA debe contar como vigente si
    # existe un hermano del mismo tipo con fecha real y todavia
    # valida -- se comprueba esto ANTES del desempate entre ciegos.
    # Un hermano con expiry_date cuenta solo si esa fecha no ha
    # pasado; un hermano con issue_date (sin expiry_date) cuenta
    # siempre, porque ese tipo de documento no caduca por si solo
    # (ver rama de arriba: el vigente es el de issue_date mas
    # reciente, nunca "ninguno" por el simple paso del tiempo).
    dated_valid_siblings = [
        s for s in siblings
        if (s.expiry_date is not None and s.expiry_date >= reference_today)
        or (s.expiry_date is None and s.issue_date is not None)
    ]
    if dated_valid_siblings:
        return False

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

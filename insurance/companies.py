# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/insurance/companies.py
"""
Group companies that hold insurance policies, with the name variants
found in policies, ledgers and folders.

---

Empresas del grupo que tienen seguros, con las variantes de nombre que
aparecen en las pólizas, en los libros mayores y en las carpetas. En el
panel la empresa nunca se escribe a mano (S146): se elige de esta lista.
Los CIF son los de CompanyFiscalProfile cuando existen.
"""
import re
import unicodedata

# (código, nombre visible, CIF, variantes de texto sin tildes)
COMPANIES = (
    ("GRA", "Grúas Álvarez", "B29405040",
     ("GRUAS ADOLFO ALVAREZ", "GRUAS ALVAREZ", "ADOLFO ALVAREZ")),
    ("TRA", "Transgrual", "B92493022", ("TRANSGRUAL",)),
    ("GLA", "Grualdi", "B29739059", ("GRUALDI",)),
    ("AGG", "Asistencia y Grúas Granada", "B93261824",
     ("ASISTENCIA Y GRUAS GRANADA", "ASIST.GRUAS GRANADA",
      "ASIST GRUAS GRANADA", "GRUAS GRANADA")),
    ("GEO", "Geogrúas", "B93654010",
     ("GEOGRUAS MONTAJES TECNICOS", "PILOTES GEOGRUAS", "GEOGRUAS")),
    ("AYO", "Álvarez y Otros", "",
     ("ALVAREZ Y OTROS",)),
    ("BEN", "Benajarafe XXI", "", ("BENAJARAFE",)),
    ("LAR", "Grúas Larios", "", ("GRUAS LARIOS", "LARIOS")),
    ("MAE", "Grúas Maestranza", "", ("GRUAS MAESTRANZA", "MAESTRANZA")),
)
CHOICES = tuple((code, label) for code, label, _cif, _v in COMPANIES)
LABELS = dict(CHOICES)
_ORDER = {code: pos for pos, (code, _l, _c, _v) in enumerate(COMPANIES)}


def plain(text):
    """
    Upper case without accents or punctuation runs.
    ---
    Mayúsculas, sin tildes y con los signos convertidos en espacios.
    """
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = text.encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", text)).strip()


def detect(*texts):
    """
    Company code named in any of the texts (longest variant wins), or "".
    ---
    Código de la empresa que nombra alguno de los textos (gana la
    variante más larga, para que «GRUAS LARIOS» no se lea como «GRUAS
    ALVAREZ»), o "" si ninguno la nombra. También por CIF.
    """
    best, best_len = "", 0
    for text in texts:
        value = plain(text)
        if not value:
            continue
        compact = value.replace(" ", "")
        for code, _label, cif, variants in COMPANIES:
            if cif and cif in compact:
                return code
            for variant in variants:
                if variant in value and len(variant) > best_len:
                    best, best_len = code, len(variant)
    return best


def label(code):
    """
    Visible name of a company code ("" if unknown).
    ---
    Nombre visible de un código de empresa.
    """
    return LABELS.get(code or "", "")


def order(code):
    """
    Sort position of a company (unknown ones last).
    ---
    Posición de orden de una empresa (las desconocidas, al final).
    """
    return _ORDER.get(code or "", len(_ORDER))

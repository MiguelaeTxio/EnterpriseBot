# C:\EnterpriseBot\AgenteFirmas\firma_nativa.py
"""
S153. Native PDF signing for the signing agent (v4): the private key of
the certificate in the Windows store signs through CNG/CryptoAPI and the
PDF is signed with pyHanko, with an appearance laid out like Acrobat's
default one (name on the left; "Firmado digitalmente por", DN and date
on the right).

---

S153. Firma nativa del agente (v4). Miguel Ángel: las empresas no
admiten las firmas que «se ven» de AutoFirma; el sello tiene que ser
como el de Adobe. AutoFirma solo deja un texto con letras básicas o una
imagen JPEG, así que el agente firma él mismo:

- la clave privada del certificado del almacén de Windows firma a
  través de Windows (CNG, o CryptoAPI para claves antiguas): nunca sale
  del ordenador;
- el PDF se firma con pyHanko (firma "adbe.pkcs7.detached", la de Adobe
  por defecto), una firma por cada sitio pedido (todas las páginas o
  solo la de la firma);
- el sello copia la disposición del de Acrobat: a la izquierda el
  nombre del certificado en grande, a la derecha «Firmado digitalmente
  por …», «Nombre de reconocimiento (DN): …» y «Fecha: aaaa.mm.dd
  hh:mm:ss +01'00'», con la letra Myriad Pro de la instalación de
  Adobe de ese ordenador (Arial si no la hay). Sin el logotipo de
  Acrobat del fondo.
"""
import asyncio
import ctypes
import datetime
import glob
import hashlib
import io
import os
import re
from ctypes import wintypes

from asn1crypto import x509
from pyhanko.pdf_utils.content import ResourceType
from pyhanko.pdf_utils.font.opentype import GlyphAccumulatorFactory
from pyhanko.pdf_utils.generic import pdf_name
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers
from pyhanko.sign.general import SigningError
from pyhanko.stamp.base import BaseStamp, BaseStampStyle
from pyhanko_certvalidator.registry import SimpleCertificateStore

# Disposición del sello de Acrobat (medida en firmas reales de Acrobat):
# interlineado 1,2; las dos columnas reparten el ancho con un hueco del
# 1 %; cada bloque se centra en vertical y la primera línea base queda
# 0,892 veces el tamaño de letra por debajo del borde de arriba.
LEADING = 1.2
COLUMN_GAP = 0.01
FIRST_BASELINE = 0.892
INNER_MARGIN = 1.0
OTHER_PAGES_BOTTOM = 24.0
DN_NAMES = {
    "2.5.4.3": "cn", "2.5.4.4": "sn", "2.5.4.42": "givenName",
    "2.5.4.5": "serialNumber", "2.5.4.10": "o", "2.5.4.11": "ou",
    "2.5.4.6": "c", "2.5.4.7": "l", "2.5.4.8": "st", "2.5.4.12": "title",
    "1.2.840.113549.1.9.1": "email",
}
FONT_GLOBS = (
    "Adobe\\*\\Resource\\Font\\MyriadPro-Regular.otf",
    "Adobe\\*\\*\\Resource\\Font\\MyriadPro-Regular.otf",
    "Adobe\\*\\*\\*\\Resource\\Font\\MyriadPro-Regular.otf",
)


# ---------------------------------------------------------------------------
# Letra
# ---------------------------------------------------------------------------


def find_font():
    """
    Myriad Pro from the local Adobe install, else Arial; (path, name).
    ---
    La Myriad Pro de la instalación de Adobe del ordenador (la que usa
    Acrobat en su sello); si no hay, Arial de Windows.
    """
    roots = [os.environ.get(name, "") for name in
             ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
    for root in filter(None, roots):
        for pattern in FONT_GLOBS:
            hits = sorted(glob.glob(os.path.join(root, pattern)))
            if hits:
                return hits[-1], "Myriad Pro"
    windir = os.environ.get("WINDIR", "C:\\Windows")
    return os.path.join(windir, "Fonts", "arial.ttf"), "Arial"


# ---------------------------------------------------------------------------
# Texto del sello
# ---------------------------------------------------------------------------


def adobe_dn(cert):
    """
    Subject DN as Acrobat shows it (reverse order, short names).
    ---
    El nombre del titular como lo escribe Acrobat: del último al primer
    atributo, nombres cortos (cn, o, c, serialNumber...) y los demás por
    su OID.
    """
    parts = []
    for rdn in reversed(list(cert.subject.chosen)):
        for ava in rdn:
            oid = ava["type"].dotted
            value = ava["value"].native
            parts.append("%s=%s" % (DN_NAMES.get(oid, oid), value))
    return ", ".join(parts)


def common_name(cert):
    """
    The subject CN (what Acrobat writes big on the left).
    ---
    El CN del titular (lo que Acrobat pone en grande a la izquierda).
    """
    subject = cert.subject
    return subject.native.get("common_name") or subject.human_friendly


def adobe_date(moment=None):
    """
    Local date as Acrobat prints it: 2026.07.23 13:55:37 +02'00'.
    ---
    La fecha local como la escribe Acrobat.
    """
    moment = (moment or datetime.datetime.now()).astimezone()
    offset = moment.utcoffset() or datetime.timedelta(0)
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return "%s %s%02d'%02d'" % (moment.strftime("%Y.%m.%d %H:%M:%S"),
                                sign, minutes // 60, minutes % 60)


def _tokens(paragraph):
    """
    Break opportunities: after spaces and after hyphens.
    ---
    Trozos de un párrafo que pueden ir en líneas distintas: se corta
    después de un espacio o de un guion (como Acrobat: "VATES-").
    """
    return [t for t in re.findall(r"[^ \-]*(?:-+| +|$)", paragraph) if t]


def wrap(paragraphs, measure, width):
    """
    Greedy wrapping of paragraphs into lines no wider than width.
    ---
    Reparte los párrafos en líneas que caben en el ancho; None si una
    palabra sola no cabe.
    """
    lines = []
    for paragraph in paragraphs:
        line = ""
        for token in _tokens(paragraph):
            candidate = line + token
            if measure(candidate.rstrip()) <= width:
                line = candidate
                continue
            if not line:
                return None
            lines.append(line.rstrip())
            line = token
            if measure(line.rstrip()) > width:
                return None
        lines.append(line.rstrip())
    return lines


def fit(paragraphs, measure_em, width, height):
    """
    Biggest font size whose wrapped text fits the column; (size, lines).
    ---
    El mayor tamaño de letra con el que el texto, repartido en líneas,
    cabe en la columna (ancho y alto).
    """
    best = None
    low, high = 0.5, 200.0
    for _ in range(40):
        size = (low + high) / 2
        lines = wrap(paragraphs, lambda s: measure_em(s) * size, width)
        if lines is not None and len(lines) * LEADING * size <= height:
            best, low = (size, lines), size
        else:
            high = size
    return best or (low, [p for p in paragraphs])


# ---------------------------------------------------------------------------
# Sello (apariencia)
# ---------------------------------------------------------------------------


def font_engine(font_path, writer):
    """
    pyHanko glyph accumulator, normalised to 1000 units per em.
    ---
    El motor de letra de pyHanko. pyHanko escribe los anchos de los
    glifos en las unidades de la letra, pero el PDF los quiere en
    milésimas de em: con letras de 1000 unidades (Myriad Pro) da igual;
    con las de 2048 (Arial) las letras saldrían separadas. Se pasa todo
    a 1000 unidades.
    """
    engine = GlyphAccumulatorFactory(
        font_path, create_objstream_if_needed=False,
    ).create_font_engine(writer)
    upem = engine.units_per_em
    if upem != 1000:
        engine.hb_font.scale = (1000, 1000)
        engine.units_per_em = 1000
        original = engine._get_cid_and_width

        def scaled(glyph_id):
            known = engine._glyphs.get(glyph_id)
            if known is not None and getattr(engine, "_scaled", None) \
                    and glyph_id in engine._scaled:
                return known
            cid, width = original(glyph_id)
            result = cid, round(width * 1000 / upem)
            engine._glyphs[glyph_id] = result
            engine._scaled = getattr(engine, "_scaled", set()) | {glyph_id}
            return result

        engine._get_cid_and_width = scaled
    return engine


class AdobeLikeStampStyle(BaseStampStyle):
    """
    Stamp style laid out like Acrobat's default signature appearance.
    ---
    Sello con la disposición del de Acrobat (sin el logotipo).
    """

    def __init__(self, font_path, name, details):
        super().__init__(border_width=0, background=None)
        object.__setattr__(self, "font_path", font_path)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "details", details)

    def create_stamp(self, writer, box, text_params):
        return AdobeLikeStamp(writer, self, box)


class AdobeLikeStamp(BaseStamp):
    """
    The stamp content: two text columns, vertically centred.
    ---
    El contenido del sello: dos columnas de texto centradas en vertical.
    """

    def _render_inner_content(self):
        style = self.style
        engine = font_engine(style.font_path, self.writer)
        self.set_resource(ResourceType.FONT, pdf_name("/F1"),
                          engine.as_resource())

        def measure_em(text):
            return engine.shape(text, with_actual_text=False).x_advance

        width = self.box.width - 2 * INNER_MARGIN
        height = self.box.height - 2 * INNER_MARGIN
        left_w = width / 2
        gap = COLUMN_GAP * width
        right_x = INNER_MARGIN + left_w + gap
        right_w = width - left_w - gap
        ops = [b"0 g"]
        for x, col_w, paragraphs in (
                (INNER_MARGIN, left_w, [style.name]),
                (right_x, right_w, style.details)):
            size, lines = fit(paragraphs, measure_em, col_w, height)
            block = len(lines) * LEADING * size
            top = INNER_MARGIN + (height - block) / 2 + block
            y = top - FIRST_BASELINE * size
            engine.font_size = size
            for line in lines:
                shaped = engine.shape(line)
                ops.append(b"BT /F1 %.3f Tf 1 0 0 1 %.4f %.4f Tm %s ET" % (
                    size, x, y, shaped.graphics_ops))
                y -= LEADING * size
        return ops


# ---------------------------------------------------------------------------
# Almacén de certificados de Windows (CNG / CryptoAPI)
# ---------------------------------------------------------------------------

CERT_STORE_PROV_SYSTEM_W = 10
CERT_SYSTEM_STORE_CURRENT_USER = 0x00010000
CERT_SYSTEM_STORE_LOCAL_MACHINE = 0x00020000
CERT_STORE_READONLY_FLAG = 0x00008000
CERT_FIND_SHA1_HASH = 0x00010000
X509_ASN_ENCODING = 0x00000001
PKCS_7_ASN_ENCODING = 0x00010000
CRYPT_ACQUIRE_CACHE_FLAG = 0x00000001
CRYPT_ACQUIRE_PREFER_NCRYPT_KEY_FLAG = 0x00020000
CERT_NCRYPT_KEY_SPEC = 0xFFFFFFFF
BCRYPT_PAD_PKCS1 = 0x00000002
PROV_RSA_AES = 24
CALG_SHA_256 = 0x0000800C
HP_HASHVAL = 0x0002
PP_CONTAINER = 6
PP_NAME = 4
CRYPT_SILENT = 0x40
MS_ENH_RSA_AES_PROV = "Microsoft Enhanced RSA and AES Cryptographic Provider"


class CERT_CONTEXT(ctypes.Structure):
    _fields_ = [("dwCertEncodingType", wintypes.DWORD),
                ("pbCertEncoded", ctypes.POINTER(ctypes.c_ubyte)),
                ("cbCertEncoded", wintypes.DWORD),
                ("pCertInfo", ctypes.c_void_p),
                ("hCertStore", ctypes.c_void_p)]


class CRYPT_HASH_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


class CERT_CHAIN_PARA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("dwUsageType", wintypes.DWORD),
                ("cUsageIdentifier", wintypes.DWORD),
                ("rgpszUsageIdentifier", ctypes.c_void_p)]


class CERT_CHAIN_ELEMENT(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("pCertContext", ctypes.POINTER(CERT_CONTEXT))]


class CERT_SIMPLE_CHAIN(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("TrustStatus", wintypes.DWORD * 2),
                ("cElement", wintypes.DWORD),
                ("rgpElement",
                 ctypes.POINTER(ctypes.POINTER(CERT_CHAIN_ELEMENT)))]


class CERT_CHAIN_CONTEXT(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("TrustStatus", wintypes.DWORD * 2),
                ("cChain", wintypes.DWORD),
                ("rgpChain",
                 ctypes.POINTER(ctypes.POINTER(CERT_SIMPLE_CHAIN)))]


class BCRYPT_PKCS1_PADDING_INFO(ctypes.Structure):
    _fields_ = [("pszAlgId", wintypes.LPCWSTR)]


def _der(context):
    return bytes(context.contents.pbCertEncoded[
        :context.contents.cbCertEncoded])


class WindowsStoreKey:
    """
    A certificate of the Windows store (by SHA-1 thumbprint) and its key.
    ---
    Un certificado del almacén de Windows (por su huella) con su cadena y
    su clave privada, que firma a través de Windows.
    """

    def __init__(self, thumbprint):
        self.crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        self.advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        self.ncrypt = ctypes.WinDLL("ncrypt", use_last_error=True)
        self._setup_prototypes()
        digest = bytes.fromhex(thumbprint)
        self.context = None
        for location in (CERT_SYSTEM_STORE_CURRENT_USER,
                         CERT_SYSTEM_STORE_LOCAL_MACHINE):
            store = self.crypt32.CertOpenStore(
                CERT_STORE_PROV_SYSTEM_W, 0, None,
                location | CERT_STORE_READONLY_FLAG, "MY")
            if not store:
                continue
            buf = (ctypes.c_ubyte * len(digest)).from_buffer_copy(digest)
            blob = CRYPT_HASH_BLOB(len(digest), buf)
            found = self.crypt32.CertFindCertificateInStore(
                store, X509_ASN_ENCODING | PKCS_7_ASN_ENCODING, 0,
                CERT_FIND_SHA1_HASH, ctypes.byref(blob), None)
            if found:
                self.context = found
                break
        if not self.context:
            raise SigningError(
                "No está en el almacén de Windows el certificado %s"
                % thumbprint)
        self.cert = x509.Certificate.load(_der(self.context))
        self.chain = self._chain()
        self._open_key()

    def _setup_prototypes(self):
        c = self.crypt32
        c.CertOpenStore.restype = ctypes.c_void_p
        c.CertOpenStore.argtypes = [ctypes.c_void_p, wintypes.DWORD,
                                    ctypes.c_void_p, wintypes.DWORD,
                                    wintypes.LPCWSTR]
        c.CertFindCertificateInStore.restype = ctypes.POINTER(CERT_CONTEXT)
        c.CertFindCertificateInStore.argtypes = [
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, ctypes.c_void_p]
        c.CertGetCertificateChain.restype = wintypes.BOOL
        c.CertGetCertificateChain.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(CERT_CONTEXT), ctypes.c_void_p,
            ctypes.c_void_p, ctypes.POINTER(CERT_CHAIN_PARA), wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.POINTER(CERT_CHAIN_CONTEXT))]
        c.CryptAcquireCertificatePrivateKey.restype = wintypes.BOOL
        c.CryptAcquireCertificatePrivateKey.argtypes = [
            ctypes.POINTER(CERT_CONTEXT), wintypes.DWORD, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.BOOL)]
        n = self.ncrypt
        n.NCryptSignHash.restype = ctypes.c_long
        n.NCryptSignHash.argtypes = [
            ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p,
            wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
        a = self.advapi32
        a.CryptGetProvParam.restype = wintypes.BOOL
        a.CryptGetProvParam.argtypes = [
            ctypes.c_size_t, wintypes.DWORD, ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
        a.CryptAcquireContextW.restype = wintypes.BOOL
        a.CryptAcquireContextW.argtypes = [
            ctypes.POINTER(ctypes.c_size_t), wintypes.LPCWSTR,
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        a.CryptCreateHash.restype = wintypes.BOOL
        a.CryptCreateHash.argtypes = [
            ctypes.c_size_t, wintypes.DWORD, ctypes.c_size_t, wintypes.DWORD,
            ctypes.POINTER(ctypes.c_size_t)]
        a.CryptSetHashParam.restype = wintypes.BOOL
        a.CryptSetHashParam.argtypes = [
            ctypes.c_size_t, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        a.CryptSignHashW.restype = wintypes.BOOL
        a.CryptSignHashW.argtypes = [
            ctypes.c_size_t, wintypes.DWORD, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
        a.CryptDestroyHash.argtypes = [ctypes.c_size_t]

    def _chain(self):
        para = CERT_CHAIN_PARA()
        para.cbSize = ctypes.sizeof(CERT_CHAIN_PARA)
        chain = ctypes.POINTER(CERT_CHAIN_CONTEXT)()
        if not self.crypt32.CertGetCertificateChain(
                None, self.context, None, None, ctypes.byref(para), 0, None,
                ctypes.byref(chain)):
            return []
        result = []
        simple = chain.contents.rgpChain[0].contents
        for index in range(1, simple.cElement):
            element = simple.rgpElement[index].contents
            result.append(x509.Certificate.load(_der(element.pCertContext)))
        return result

    def _open_key(self):
        handle = ctypes.c_size_t()
        spec = wintypes.DWORD()
        free = wintypes.BOOL()
        if not self.crypt32.CryptAcquireCertificatePrivateKey(
                self.context,
                CRYPT_ACQUIRE_CACHE_FLAG
                | CRYPT_ACQUIRE_PREFER_NCRYPT_KEY_FLAG,
                None, ctypes.byref(handle), ctypes.byref(spec),
                ctypes.byref(free)):
            raise SigningError(
                "Windows no da acceso a la clave privada del certificado "
                "(error %d)" % ctypes.get_last_error())
        self.key_handle = handle.value
        self.key_spec = spec.value
        if self.key_spec != CERT_NCRYPT_KEY_SPEC:
            # Clave antigua (CryptoAPI): se vuelve a abrir el mismo
            # contenedor con el proveedor que sabe SHA-256.
            container = self._prov_text(PP_CONTAINER)
            aes = ctypes.c_size_t()
            if not self.advapi32.CryptAcquireContextW(
                    ctypes.byref(aes), container, MS_ENH_RSA_AES_PROV,
                    PROV_RSA_AES, 0):
                raise SigningError(
                    "No se puede abrir la clave antigua con SHA-256 "
                    "(error %d)" % ctypes.get_last_error())
            self.key_handle = aes.value

    def _prov_text(self, param):
        size = wintypes.DWORD(0)
        self.advapi32.CryptGetProvParam(self.key_handle, param, None,
                                        ctypes.byref(size), 0)
        buf = ctypes.create_string_buffer(size.value)
        if not self.advapi32.CryptGetProvParam(
                self.key_handle, param, buf, ctypes.byref(size), 0):
            raise SigningError("No se puede leer el contenedor de la clave")
        return buf.value.decode("mbcs")

    def sign_sha256(self, digest):
        """
        RSA PKCS#1 v1.5 signature of a SHA-256 digest.
        ---
        Firma RSA (PKCS#1 v1.5) de un resumen SHA-256, hecha por Windows.
        """
        if self.key_spec == CERT_NCRYPT_KEY_SPEC:
            info = BCRYPT_PKCS1_PADDING_INFO("SHA256")
            digest_buf = ctypes.create_string_buffer(digest, len(digest))
            size = wintypes.DWORD()
            status = self.ncrypt.NCryptSignHash(
                self.key_handle, ctypes.byref(info), digest_buf,
                len(digest), None, 0, ctypes.byref(size), BCRYPT_PAD_PKCS1)
            if status:
                raise SigningError("NCryptSignHash: 0x%08X"
                                   % (status & 0xFFFFFFFF))
            out = ctypes.create_string_buffer(size.value)
            status = self.ncrypt.NCryptSignHash(
                self.key_handle, ctypes.byref(info), digest_buf,
                len(digest), out, size.value, ctypes.byref(size),
                BCRYPT_PAD_PKCS1)
            if status:
                raise SigningError("NCryptSignHash: 0x%08X"
                                   % (status & 0xFFFFFFFF))
            return out.raw[:size.value]
        hash_handle = ctypes.c_size_t()
        a = self.advapi32
        if not a.CryptCreateHash(self.key_handle, CALG_SHA_256, 0, 0,
                                 ctypes.byref(hash_handle)):
            raise SigningError("CryptCreateHash: %d" % ctypes.get_last_error())
        try:
            digest_buf = ctypes.create_string_buffer(digest, len(digest))
            if not a.CryptSetHashParam(hash_handle, HP_HASHVAL, digest_buf,
                                       0):
                raise SigningError("CryptSetHashParam: %d"
                                   % ctypes.get_last_error())
            size = wintypes.DWORD()
            a.CryptSignHashW(hash_handle, self.key_spec, None, 0, None,
                             ctypes.byref(size))
            out = ctypes.create_string_buffer(size.value)
            if not a.CryptSignHashW(hash_handle, self.key_spec, None, 0, out,
                                    ctypes.byref(size)):
                raise SigningError("CryptSignHash: %d"
                                   % ctypes.get_last_error())
            # CryptoAPI devuelve la firma al revés (little-endian).
            return out.raw[:size.value][::-1]
        finally:
            a.CryptDestroyHash(hash_handle)


class WindowsStoreSigner(signers.Signer):
    """
    pyHanko signer backed by a key of the Windows store.
    ---
    Firmante de pyHanko que firma con la clave del almacén de Windows.
    """

    def __init__(self, key):
        self.key = key
        super().__init__(
            signing_cert=key.cert,
            cert_registry=SimpleCertificateStore.from_certs(key.chain),
        )

    async def async_sign_raw(self, data, digest_algorithm, dry_run=False):
        if digest_algorithm.lower() != "sha256":
            raise SigningError("Solo SHA-256 (pedido %s)" % digest_algorithm)
        size = self.key.cert.public_key.bit_size // 8
        if dry_run:
            return bytes(size)
        return self.key.sign_sha256(hashlib.sha256(data).digest())


# ---------------------------------------------------------------------------
# Firma del PDF
# ---------------------------------------------------------------------------


def parse_config(config):
    """
    Page and box from the AutoFirma-style visible signature config.
    ---
    Página y recuadro de la firma visible (configuración de AutoFirma
    que manda el panel); None si no hay.
    """
    values = dict(line.split("=", 1) for line in (config or "").splitlines()
                  if "=" in line)
    try:
        return (int(values["signaturePage"]),
                (float(values["signaturePositionOnPageLowerLeftX"]),
                 float(values["signaturePositionOnPageLowerLeftY"]),
                 float(values["signaturePositionOnPageUpperRightX"]),
                 float(values["signaturePositionOnPageUpperRightY"])))
    except (KeyError, ValueError):
        return None


def placements(pdf_bytes, config, all_pages):
    """
    [(page 1-based, box)] where to sign.
    ---
    Dónde firmar: el recuadro de la firma y, con «todas las páginas», el
    mismo recuadro al pie de cada una de las demás (como hace Acrobat
    cuando se firma página a página).
    """
    from pyhanko.pdf_utils.reader import PdfFileReader

    main = parse_config(config)
    reader = PdfFileReader(io.BytesIO(pdf_bytes), strict=False)
    total = int(reader.root["/Pages"]["/Count"])
    if main is None:
        main = (total, (190.0, OTHER_PAGES_BOTTOM, 330.0,
                        OTHER_PAGES_BOTTOM + 52.0))
    page, (llx, lly, urx, ury) = main
    page = min(max(page, 1), total)
    if not all_pages:
        return [(page, (llx, lly, urx, ury))]
    height = ury - lly
    result = []
    for number in range(1, total + 1):
        if number == page:
            result.append((number, (llx, lly, urx, ury)))
        else:
            result.append((number, (llx, OTHER_PAGES_BOTTOM, urx,
                                    OTHER_PAGES_BOTTOM + height)))
    return result


def _existing_names(pdf_bytes):
    from pyhanko.pdf_utils.reader import PdfFileReader

    reader = PdfFileReader(io.BytesIO(pdf_bytes), strict=False)
    names = set()
    form = reader.root.get("/AcroForm")
    if form:
        for ref in form.get_object().get("/Fields", []):
            title = ref.get_object().get("/T")
            if title:
                names.add(str(title))
    return names


def sign_pdf(pdf_bytes, signer, places, font_path):
    """
    Sign the PDF once per placement (incremental revisions).
    ---
    Firma el PDF una vez por cada sitio (una revisión tras otra, como
    Acrobat), con el sello al estilo de Acrobat.
    """
    cert = signer.signing_cert
    name = common_name(cert)
    dn = adobe_dn(cert)
    taken = _existing_names(pdf_bytes)
    counter = 1
    data = pdf_bytes
    for page, box in places:
        counter += 1
        while "Signature%d" % counter in taken:
            counter += 1
        field = "Signature%d" % counter
        taken.add(field)
        details = ["Firmado digitalmente por %s" % name,
                   "Nombre de reconocimiento (DN): %s" % dn,
                   "Fecha: %s" % adobe_date()]
        style = AdobeLikeStampStyle(font_path, name, details)
        meta = signers.PdfSignatureMetadata(
            field_name=field, md_algorithm="sha256",
            subfilter=fields.SigSeedSubFilter.ADOBE_PKCS7_DETACHED,
            name=name)
        pdf_signer = signers.PdfSigner(
            meta, signer=signer, stamp_style=style,
            new_field_spec=fields.SigFieldSpec(
                sig_field_name=field, on_page=page - 1,
                box=tuple(round(v, 3) for v in box)))
        writer = IncrementalPdfFileWriter(io.BytesIO(data), strict=False)
        out = io.BytesIO()
        asyncio.run(pdf_signer.async_sign_pdf(writer, output=out))
        data = out.getvalue()
    return data

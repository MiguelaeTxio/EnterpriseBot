# C:\EnterpriseBot\AgenteFirmas\prueba_firma_nativa.py
"""
S153. CI check of the native signing (Windows runner, test certificates).
---
Prueba de la firma nativa en el runner Windows del workflow (no va en el
.exe): firma un PDF de 3 páginas con dos certificados de prueba del
almacén de Windows (clave CNG y clave antigua de CryptoAPI), en todas
las páginas, y comprueba con pyHanko que cada firma está íntegra y es
criptográficamente correcta. Sale con error si algo falla.
"""
import io
import sys

from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature

import firma_nativa


def sample_pdf(pages=3):
    """
    A minimal PDF with blank A4 pages.
    ---
    Un PDF mínimo con páginas A4 en blanco.
    """
    from pyhanko.pdf_utils import generic, writer

    out = writer.PdfFileWriter()
    for _ in range(pages):
        page = writer.PageObject(
            contents=out.add_object(generic.StreamObject(stream_data=b"")),
            media_box=generic.ArrayObject(
                [generic.NumberObject(v) for v in (0, 0, 595, 842)]))
        out.insert_page(page)
    buf = io.BytesIO()
    out.write(buf)
    return buf.getvalue()


def main(thumbprints):
    font_path, font_name = firma_nativa.find_font()
    print("Letra:", font_name, font_path)
    pdf = sample_pdf()
    config = ("signaturePage=2\nsignaturePositionOnPageLowerLeftX=189\n"
              "signaturePositionOnPageLowerLeftY=100\n"
              "signaturePositionOnPageUpperRightX=325\n"
              "signaturePositionOnPageUpperRightY=151")
    failures = 0
    for thumbprint in thumbprints:
        key = firma_nativa.WindowsStoreKey(thumbprint)
        kind = ("CNG" if key.key_spec == firma_nativa.CERT_NCRYPT_KEY_SPEC
                else "CryptoAPI")
        signer = firma_nativa.WindowsStoreSigner(key)
        places = firma_nativa.placements(pdf, config, True)
        signed = firma_nativa.sign_pdf(pdf, signer, places, font_path)
        reader = PdfFileReader(io.BytesIO(signed))
        sigs = reader.embedded_signatures
        print(thumbprint, kind, firma_nativa.common_name(key.cert),
              "firmas:", len(sigs))
        print("  DN:", firma_nativa.adobe_dn(key.cert))
        if len(sigs) != len(places):
            failures += 1
        for sig in sigs:
            status = validate_pdf_signature(sig)
            print("  ", sig.field_name, "integra:", status.intact,
                  "correcta:", status.valid,
                  sig.sig_object.get("/SubFilter"))
            if not (status.intact and status.valid):
                failures += 1
        with open("firmado_%s.pdf" % kind, "wb") as handle:
            handle.write(signed)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main(sys.argv[1:])

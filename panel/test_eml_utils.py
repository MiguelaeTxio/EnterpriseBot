# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/test_eml_utils.py
"""
Regression test of the `.eml` line endings (S157).

---

Test de regresión de los saltos de línea de los `.eml` (S157): con
saltos LF, Outlook clásico rompía el quoted-printable del cuerpo HTML
(`sal=do`, `<=ul>`, `U= saludo`).
"""
import email
import re
import unittest
from email import policy
from email.message import EmailMessage

from panel.eml_utils import eml_bytes


LONG_HTML = (
    "<html><body><p>Buenos días:</p><p>Les adjuntamos la documentación "
    "de la máquina A-35 que nos solicitaron: ficha técnica, inspección "
    "periódica, certificado CE y declaración de conformidad.</p><ul>"
    + "".join(
        "<li>Documento número %d con descripción larga y acentuada "
        "(revisión, inspección, señalización)</li>" % n
        for n in range(1, 30)
    )
    + "</ul><p>Quedamos a su disposición para cualquier aclaración."
    "</p><p>Un saludo.</p></body></html>"
)


def _draft():
    msg = EmailMessage()
    msg["Subject"] = "Documentación maquinaria A-35"
    msg["X-Unsent"] = "1"
    msg.set_content("Documentación adjunta.")
    msg.add_alternative(LONG_HTML, subtype="html")
    msg.add_attachment(b"%PDF-1.4 prueba", maintype="application",
                       subtype="pdf", filename="dosier.pdf")
    return msg


class EmlBytesTests(unittest.TestCase):
    """
    eml_bytes writes CRLF and keeps the HTML body intact.

    ---

    eml_bytes escribe CRLF y conserva intacto el cuerpo HTML.
    """

    def test_every_line_ends_with_crlf(self):
        data = eml_bytes(_draft())
        self.assertIsNone(re.search(rb"(?<!\r)\n", data))
        self.assertIn(b"=\r\n", data)

    def test_html_body_round_trips(self):
        parsed = email.message_from_bytes(
            eml_bytes(_draft()), policy=policy.default,
        )
        html = parsed.get_body(preferencelist=("html",)).get_content()
        self.assertEqual(html.replace("\r\n", "\n").rstrip("\n"),
                         LONG_HTML)


if __name__ == "__main__":
    unittest.main()

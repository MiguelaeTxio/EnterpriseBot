# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/panel/eml_utils.py
"""
Serialization of the `.eml` drafts the panel builds (S157).

`bytes(msg)` writes the message with bare LF line endings. The HTML
body goes in quoted-printable, whose soft line break is `=` at the end
of a line; Outlook expects CRLF, reads `=\\n` as an `=XY` escape and
eats the break plus the next character (`sal=\\nudo` ends up as
`sal=do`). Every `.eml` of the panel is written with CRLF.

---

Serialización de los borradores `.eml` que genera el panel (S157).

`bytes(msg)` escribe el mensaje con saltos LF sueltos. El cuerpo HTML
va en quoted-printable, cuyo salto blando es un `=` al final de la
línea; Outlook espera CRLF, toma `=\\n` como un escape `=XY` y se come
el salto y el carácter siguiente (`sal=\\nudo` acaba como `sal=do`).
Todos los `.eml` del panel se escriben con CRLF.
"""


def eml_bytes(msg) -> bytes:
    """
    The message as bytes with CRLF line endings.

    ---

    El mensaje en bytes con saltos de línea CRLF, para que Outlook
    clásico decodifique bien el quoted-printable del cuerpo.
    """
    return msg.as_bytes(policy=msg.policy.clone(linesep="\r\n"))

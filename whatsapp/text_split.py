# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/whatsapp/text_split.py
"""
Split a long WhatsApp text into messages Twilio accepts.

---

S149 (Miguel Ángel, 20/11, Paloma no recibía el texto del alta al pulsar
«Leer aquí»): WhatsApp por Twilio no admite más de 1600 caracteres por
mensaje (error 21617) y rechaza el mensaje entero. Se parte por
párrafos (líneas en blanco), luego por líneas y, si una línea sola no
cabe, por palabras; cada trozo, como mucho LIMIT caracteres.
"""

LIMIT = 1500


def _pieces(text, sep, limit):
    """Join `sep`-separated pieces greedily up to `limit` characters."""
    parts, current = [], ""
    for piece in text.split(sep):
        candidate = piece if not current else current + sep + piece
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
        current = piece
    if current:
        parts.append(current)
    return parts


def split_whatsapp_text(text, limit=LIMIT):
    """
    [text] if it fits, else the text in several pieces of <= limit.
    ---
    El texto en uno o varios trozos de como mucho `limit` caracteres,
    cortando por párrafos, líneas o palabras (nunca a media palabra
    salvo una palabra más larga que el límite).
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return [text] if text else []
    result = []
    for paragraph_group in _pieces(text, "\n\n", limit):
        if len(paragraph_group) <= limit:
            result.append(paragraph_group)
            continue
        for line_group in _pieces(paragraph_group, "\n", limit):
            if len(line_group) <= limit:
                result.append(line_group)
                continue
            for word_group in _pieces(line_group, " ", limit):
                while len(word_group) > limit:
                    result.append(word_group[:limit])
                    word_group = word_group[limit:]
                if word_group:
                    result.append(word_group)
    return [part.strip() for part in result if part.strip()]

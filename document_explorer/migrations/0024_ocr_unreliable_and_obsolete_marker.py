# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0024_ocr_unreliable_and_obsolete_marker.py
"""
H30 (S48). Dos campos nuevos, decididos en la misma sesion tras el
diseño real del flujo de subida desde ficha:

- `DocumentTypeCatalog.ocr_unreliable`: cuando la lectura OCR de un
  tipo documental es estructuralmente poco fiable (verificado con
  datos reales: tarjetas ITV manuscritas con fondo de seguridad
  "ESPAÑA" que domina la lectura de Tesseract, ver anexo H30 seccion
  "COMPLETADAS EN S48"), la contrastacion de la fecha introducida por
  el supervisor pasa por Gemini en vez de por OCR local. Vive como
  dato en el catalogo, nunca como lista fija en codigo -- mismo
  principio ya aplicado a tracks_expiry (S045).
- `DocumentIndexEntry.is_obsolete`: marcador persistido para la
  trazabilidad real del libro de historial -- Miguel Angel, verbatim
  (S48): "quitar la ITV anterior, ponerla en obsoletas... sino
  marcandola como obsoleta, que es la actualizacion que le vamos a
  dar, para que siempre haya una trazabilidad y un registro
  historico". Sustituye el movimiento fisico a una carpeta
  "OBSOLETOS" por un campo de estado -- 4.12 sigue aplicando (nunca
  se mueve ni se borra el objeto real).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document_explorer", "0023_seed_baja_medica_investigacion_accidente"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttypecatalog",
            name="ocr_unreliable",
            field=models.BooleanField(
                default=False,
                verbose_name="OCR poco fiable",
                help_text=(
                    "H30 (S48). Cuando la lectura OCR de este tipo es "
                    "estructuralmente poco fiable (verificado con datos "
                    "reales, no supuesto), la contrastacion de la "
                    "fecha introducida por el supervisor pasa por "
                    "Gemini en vez de por OCR local. Activar desde "
                    "aqui, sin tocar codigo, cuando aparezca otro tipo "
                    "con el mismo problema."
                ),
            ),
        ),
        migrations.AddField(
            model_name="documentindexentry",
            name="is_obsolete",
            field=models.BooleanField(
                default=False,
                verbose_name="Obsoleto",
                help_text=(
                    "H30 (S48). Marcador persistido de trazabilidad: "
                    "True cuando un documento mas reciente del mismo "
                    "tipo y mismo sujeto lo ha sustituido "
                    "(document_management.vigencia_service."
                    "evaluate_substitution()). Nunca se mueve ni se "
                    "borra el archivo real (4.12) -- solo cambia este "
                    "campo, para conservar el historico completo "
                    "(libro de revisiones/reparaciones)."
                ),
            ),
        ),
    ]

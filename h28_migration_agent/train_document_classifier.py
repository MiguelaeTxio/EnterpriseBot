# C:\EnterpriseBot\h28_migration_agent\train_document_classifier.py
"""
H30 (S54). Entrena y VALIDA un modelo real de clasificacion de tipo
documental a partir del conjunto de entrenamiento extraido por
`extract_training_dataset.py` (documentos ya clasificados, texto OCR
real) mas `data_imports/web_templates.jsonl` (plantillas genericas
reales para tipos con pocos ejemplos).

Diseño acordado con Miguel Angel: nada de reglas de texto fijas
(`CONTENT_MARKERS`) sacadas de 2-3 muestras -- un modelo real
entrenado sobre los datos que YA tenemos clasificados, con
caracteristicas de texto (TF-IDF) + carpeta + nombre de archivo,
clasificador lineal (regresion logistica), y validacion honesta
train/test ANTES de aplicar nada a lo desconocido.

Nunca toca la base de datos ni GCS -- solo lee los .jsonl locales
y escribe el modelo entrenado a disco (`document_classifier.joblib`).

USO:
    python train_document_classifier.py dataset*.jsonl data_imports/web_templates.jsonl
    python train_document_classifier.py dataset*.jsonl data_imports/web_templates.jsonl --min-examples 5
"""
import argparse
import json
import sys
from collections import Counter

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


def cargar_dataset(paths):
    filas = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    filas.append(json.loads(linea))
                except json.JSONDecodeError:
                    continue
    return filas


def texto_combinado(fila):
    # Carpeta + nombre + texto OCR, combinados en un unico campo para
    # que TF-IDF capture señal de los tres sitios a la vez -- igual
    # que en un modelo de deteccion de fraude, ningun campo decide
    # solo, todos suman.
    return " ".join([
        fila.get("parent_path", "") or "",
        fila.get("name", "") or "",
        fila.get("texto", "") or "",
    ])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("datasets", nargs="+", help="Archivos .jsonl de entrada")
    parser.add_argument("--min-examples", type=int, default=5,
                         help="Tipos con menos ejemplos que esto se excluyen "
                              "del entrenamiento (demasiado pocos para "
                              "aprender nada fiable) y se listan aparte.")
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--output", default="document_classifier.joblib")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    filas = cargar_dataset(args.datasets)
    print("Filas cargadas en total: %d (de %d archivos)"
          % (len(filas), len(args.datasets)))

    por_tipo = Counter(f["tipo"] for f in filas)
    excluidos = {t for t, n in por_tipo.items() if n < args.min_examples}
    if excluidos:
        print("\n⛔ Tipos EXCLUIDOS del entrenamiento (menos de %d ejemplos, "
              "no hay base estadistica suficiente):" % args.min_examples)
        for t in sorted(excluidos):
            print("    %-30s %d ejemplos" % (t, por_tipo[t]))

    filas_usables = [f for f in filas if f["tipo"] not in excluidos]
    if not filas_usables:
        sys.exit("No queda ningun tipo con suficientes ejemplos. Nada que entrenar.")

    X_texto = [texto_combinado(f) for f in filas_usables]
    y = [f["tipo"] for f in filas_usables]

    print("\nTipos incluidos en el entrenamiento: %d" % len(set(y)))
    print("Documentos totales usados: %d\n" % len(y))

    # Estratificado: cada tipo se reparte proporcionalmente entre
    # entrenamiento y prueba, para que la validacion sea honesta en
    # TODOS los tipos, no solo en los mas frecuentes.
    X_train, X_test, y_train, y_test = train_test_split(
        X_texto, y, test_size=args.test_size, random_state=args.seed,
        stratify=y,
    )

    print("Entrenamiento: %d documentos | Prueba (nunca vistos): %d documentos\n"
          % (len(X_train), len(X_test)))

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            max_features=20000,
            ngram_range=(1, 2),
            min_df=2,
            sublinear_tf=True,
        )),
        ("clf", LogisticRegression(
            max_iter=2000,
            class_weight="balanced",  # compensa que unos tipos tengan
            # muchos mas ejemplos que otros (p.ej. BAJA_PERSONAL con
            # miles frente a EXCEDENCIA con 4) -- sin esto el modelo
            # aprenderia sobre todo los tipos mayoritarios.
            random_state=args.seed,
        )),
    ])

    print("Entrenando ...")
    pipeline.fit(X_train, y_train)

    print("\nValidando contra el conjunto de PRUEBA (nunca visto durante "
          "el entrenamiento) ...\n")
    y_pred = pipeline.predict(X_test)

    acierto_global = accuracy_score(y_test, y_pred)
    print("=== ACIERTO GLOBAL REAL: %.1f%% ===\n" % (100 * acierto_global))

    print(classification_report(y_test, y_pred, zero_division=0))

    joblib.dump({
        "pipeline": pipeline,
        "tipos_excluidos": sorted(excluidos),
        "min_examples": args.min_examples,
    }, args.output)
    print("\nModelo guardado en: %s" % args.output)
    print(
        "\nEste modelo NO debe usarse sobre documentos desconocidos sin "
        "revisar antes el classification_report de arriba tipo por "
        "tipo -- un acierto global alto puede esconder tipos concretos "
        "con acierto muy bajo."
    )


if __name__ == "__main__":
    main()

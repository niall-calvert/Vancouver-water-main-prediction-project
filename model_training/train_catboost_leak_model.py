import json
from pathlib import Path

import joblib
import pandas as pd

from sqlalchemy import create_engine

from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    average_precision_score,
)

from catboost import CatBoostClassifier


DB_URL = "postgresql+psycopg2://myuser:mypassword@localhost:5432/apidata"
TABLE_NAME = "final_model_data"

MODEL_PATH = "catboost_leak_model.joblib"
PREDICTIONS_CSV = "pipe_leak_predictions_2025_catboost.csv"
PREDICTIONS_LINES_GEOJSON = "docs/predictions_catboost_lines.geojson"
PREDICTIONS_JSON = "docs/predictions_catboost.json"


NUMERIC_FEATURES = [
    "diameter_mm",
    "installation_year",
    "lon",
    "lat",
    "pipe_age",
    "leaked_that_year",
    "leak_count_that_year",
    "years_since_last_leak",
    "most_recent_leak_year",
    "nearest_leak_distance_m",
    "average_leak_distance_m",
]

CATEGORICAL_FEATURES = [
    "source_dataset",
    "lining_material",
    "material",
]

FEATURE_COLS = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def load_data():
    engine = create_engine(DB_URL)
    query = f"""
        SELECT *
        FROM {TABLE_NAME}
        WHERE leaks_next_year IS NOT NULL;
    """
    return pd.read_sql(query, engine)


def prepare_data(df):
    df = df.copy()

    df["leaks_next_year"] = df["leaks_next_year"].astype(int)

    for col in CATEGORICAL_FEATURES:
        df[col] = df[col].fillna("Unknown").astype(str)

    for col in NUMERIC_FEATURES:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def calculate_metrics(y_true, probabilities, threshold):
    predictions = (probabilities >= threshold).astype(int)

    tp = ((predictions == 1) & (y_true == 1)).sum()
    tn = ((predictions == 0) & (y_true == 0)).sum()
    fp = ((predictions == 1) & (y_true == 0)).sum()
    fn = ((predictions == 0) & (y_true == 1)).sum()

    precision = tp / (tp + fp) if tp + fp > 0 else 0
    recall = tp / (tp + fn) if tp + fn > 0 else 0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall > 0
        else 0
    )

    return {
        "threshold": threshold,
        "tp": int(tp),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "predicted_positive_count": int(tp + fp),
    }


def find_best_threshold(y_true, probabilities):
    rows = []

    for i in range(1, 100):
        threshold = i / 100
        rows.append(calculate_metrics(y_true, probabilities, threshold))

    threshold_df = pd.DataFrame(rows).sort_values("f1", ascending=False)
    threshold_df.to_csv("catboost_threshold_tuning_results.csv", index=False)

    best = threshold_df.iloc[0]

    print("\nBest validation threshold by F1")
    print("=" * 40)
    print(f"Threshold: {best['threshold']:.2f}")
    print(f"Precision: {best['precision']:.4f}")
    print(f"Recall:    {best['recall']:.4f}")
    print(f"F1:        {best['f1']:.4f}")
    print(f"Predicted positives: {int(best['predicted_positive_count']):,}")

    return float(best["threshold"])


def evaluate(model, X, y, label, threshold):
    probabilities = model.predict_proba(X)[:, 1]
    predictions = (probabilities >= threshold).astype(int)

    print(f"\n{label}")
    print("=" * 40)
    print(f"Threshold: {threshold:.2f}")

    print("\nConfusion matrix:")
    print(confusion_matrix(y, predictions))

    print("\nClassification report:")
    print(classification_report(y, predictions, zero_division=0))

    print(f"ROC AUC: {roc_auc_score(y, probabilities):.4f}")
    print(f"PR AUC: {average_precision_score(y, probabilities):.4f}")

    metrics = calculate_metrics(y, probabilities, threshold)

    print("\nLeak-class summary:")
    print(f"Precision: {metrics['precision']:.4f}")
    print(f"Recall:    {metrics['recall']:.4f}")
    print(f"F1:        {metrics['f1']:.4f}")
    print(f"Predicted leak rows: {metrics['predicted_positive_count']:,}")

    return probabilities, predictions, metrics


def export_predictions(df, model, threshold):
    scoring_df = df[df["analysis_year"] == 2025].copy()

    if scoring_df.empty:
        print("\nNo 2025 rows found for scoring.")
        return

    X_score = scoring_df[FEATURE_COLS]

    scoring_df["leak_probability_next_year"] = model.predict_proba(X_score)[:, 1]
    scoring_df["predicted_leak_next_year"] = (
        scoring_df["leak_probability_next_year"] >= threshold
    ).astype(int)

    scoring_df["risk_rank"] = scoring_df["leak_probability_next_year"].rank(
        ascending=False,
        method="first",
    ).astype(int)

    output_cols = [
        "pipe_id",
        "analysis_year",
        "source_dataset",
        "diameter_mm",
        "installation_year",
        "lining_material",
        "material",
        "lon",
        "lat",
        "pipe_age",
        "leaked_that_year",
        "leak_count_that_year",
        "years_since_last_leak",
        "most_recent_leak_year",
        "nearest_leak_distance_m",
        "average_leak_distance_m",
        "leak_probability_next_year",
        "predicted_leak_next_year",
        "risk_rank",
    ]

    scoring_df = scoring_df[output_cols].sort_values(
        "leak_probability_next_year",
        ascending=False,
    )

    scoring_df.to_csv(PREDICTIONS_CSV, index=False)

    Path(PREDICTIONS_JSON).parent.mkdir(parents=True, exist_ok=True)

    top_predictions = scoring_df.head(5000)
    records = top_predictions.to_dict(orient="records")

    with open(PREDICTIONS_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f)

    print(f"\nSaved {PREDICTIONS_CSV}")
    print(f"Saved {PREDICTIONS_JSON}")

    # ------------------------------------------------------------
    # Export pipe-line GeoJSON for map visualization
    # ------------------------------------------------------------
    engine = create_engine(DB_URL)

    pipe_geom_df = pd.read_sql(
        """
        SELECT
            id AS pipe_id,
            geom
        FROM main
        WHERE geom IS NOT NULL;
        """,
        engine,
    )

    map_df = scoring_df.merge(
        pipe_geom_df,
        on="pipe_id",
        how="left",
    )

    # Optional: only export the highest-risk pipes to keep GitHub Pages fast.
    map_df = map_df[map_df["predicted_leak_next_year"] == 1].copy()

    features = []

    for _, row in map_df.iterrows():
        geom = row["geom"]

        if geom is None:
            continue

        # Depending on how pandas reads JSONB, geom may already be a dict
        # or it may be a JSON string.
        if isinstance(geom, str):
            try:
                geom = json.loads(geom)
            except json.JSONDecodeError:
                continue

        # Your main.geom is a GeoJSON Feature:
        # {
        #   "type": "Feature",
        #   "geometry": {"type": "LineString", "coordinates": [...]},
        #   "properties": {}
        # }
        if isinstance(geom, dict) and geom.get("type") == "Feature":
            geometry = geom.get("geometry")
        else:
            geometry = geom

        if not geometry:
            continue

        feature = {
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "pipe_id": int(row["pipe_id"]),
                "analysis_year": int(row["analysis_year"]),
                "source_dataset": row["source_dataset"],
                "diameter_mm": None if pd.isna(row["diameter_mm"]) else float(row["diameter_mm"]),
                "installation_year": None if pd.isna(row["installation_year"]) else int(row["installation_year"]),
                "lining_material": row["lining_material"],
                "material": row["material"],
                "pipe_age": None if pd.isna(row["pipe_age"]) else float(row["pipe_age"]),
                "leaked_that_year": None if pd.isna(row["leaked_that_year"]) else int(row["leaked_that_year"]),
                "leak_count_that_year": None if pd.isna(row["leak_count_that_year"]) else int(row["leak_count_that_year"]),
                "years_since_last_leak": None if pd.isna(row["years_since_last_leak"]) else float(row["years_since_last_leak"]),
                "most_recent_leak_year": None if pd.isna(row["most_recent_leak_year"]) else int(row["most_recent_leak_year"]),
                "nearest_leak_distance_m": None if pd.isna(row["nearest_leak_distance_m"]) else float(row["nearest_leak_distance_m"]),
                "average_leak_distance_m": None if pd.isna(row["average_leak_distance_m"]) else float(row["average_leak_distance_m"]),
                "leak_probability_next_year": float(row["leak_probability_next_year"]),
                "predicted_leak_next_year": int(row["predicted_leak_next_year"]),
                "risk_rank": int(row["risk_rank"]),
            },
        }

        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    with open(PREDICTIONS_LINES_GEOJSON, "w", encoding="utf-8") as f:
        json.dump(geojson, f)

    print(f"Saved {PREDICTIONS_LINES_GEOJSON}")

    print("\n2025 scoring summary:")
    print(
        scoring_df["predicted_leak_next_year"]
        .value_counts()
        .sort_index()
        .rename(index={0: "predicted_no_leak", 1: "predicted_leak"})
    )


def main():
    df = load_data()
    df = prepare_data(df)

    print(f"Loaded {len(df):,} rows")

    train_df = df[df["analysis_year"].between(2016, 2022)].copy()
    val_df = df[df["analysis_year"] == 2023].copy()
    test_df = df[df["analysis_year"] == 2024].copy()

    print(f"Train rows: {len(train_df):,}")
    print(f"Validation rows: {len(val_df):,}")
    print(f"Test rows: {len(test_df):,}")

    positives = train_df["leaks_next_year"].sum()
    negatives = len(train_df) - positives
    scale_pos_weight = negatives / positives if positives > 0 else 1

    print(f"Training positives: {positives:,}")
    print(f"Training negatives: {negatives:,}")
    print(f"scale_pos_weight: {scale_pos_weight:.2f}")

    X_train = train_df[FEATURE_COLS]
    y_train = train_df["leaks_next_year"]

    X_val = val_df[FEATURE_COLS]
    y_val = val_df["leaks_next_year"]

    X_test = test_df[FEATURE_COLS]
    y_test = test_df["leaks_next_year"]

    cat_feature_indices = [
        FEATURE_COLS.index(col) for col in CATEGORICAL_FEATURES
    ]

    model = CatBoostClassifier(
        iterations=700,
        learning_rate=0.05,
        depth=6,
        loss_function="Logloss",
        eval_metric="PRAUC",
        auto_class_weights="Balanced",
        bootstrap_type="MVS",
        random_seed=42,
        verbose=100,
        allow_writing_files=False,
    )

    print("\nTraining CatBoost model...")
    model.fit(
        X_train,
        y_train,
        cat_features=cat_feature_indices,
        eval_set=(X_val, y_val),
        use_best_model=True,
    )

    val_probabilities = model.predict_proba(X_val)[:, 1]
    best_threshold = find_best_threshold(y_val, val_probabilities)

    evaluate(model, X_val, y_val, "Validation results", best_threshold)
    evaluate(model, X_test, y_test, "Test results", best_threshold)

    joblib.dump(
        {
            "model": model,
            "feature_cols": FEATURE_COLS,
            "categorical_features": CATEGORICAL_FEATURES,
            "best_threshold": best_threshold,
            "scale_pos_weight": scale_pos_weight,
        },
        MODEL_PATH,
    )

    print(f"\nSaved model to {MODEL_PATH}")

    export_predictions(df, model, best_threshold)


if __name__ == "__main__":
    main()
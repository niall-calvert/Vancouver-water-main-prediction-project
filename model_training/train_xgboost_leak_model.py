import json
from pathlib import Path

import joblib
import pandas as pd

from sqlalchemy import create_engine

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    average_precision_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from xgboost import XGBClassifier


DB_URL = "postgresql+psycopg2://myuser:mypassword@localhost:5432/apidata"
TABLE_NAME = "final_model_data"

MODEL_PATH = "xgboost_leak_model.joblib"
PREDICTIONS_CSV = "pipe_leak_predictions_2025.csv"
PREDICTIONS_JSON = "docs/predictions.json"


def load_data():
    engine = create_engine(DB_URL)

    query = f"""
        SELECT *
        FROM {TABLE_NAME}
        WHERE leaks_next_year IS NOT NULL;
    """

    return pd.read_sql(query, engine)


def get_feature_columns():
    numeric_features = [
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

    categorical_features = [
        "source_dataset",
        "lining_material",
        "material",
    ]

    return numeric_features, categorical_features


def build_model(scale_pos_weight):
    numeric_features, categorical_features = get_feature_columns()

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "num",
                SimpleImputer(strategy="median"),
                numeric_features,
            ),
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical_features,
            ),
        ]
    )

    model = XGBClassifier(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        objective="binary:logistic",
        eval_metric="aucpr",
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        n_jobs=-1,
    )

    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", model),
        ]
    )

    feature_cols = numeric_features + categorical_features

    return pipeline, feature_cols


def calculate_classification_metrics(y_true, probabilities, threshold):
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
        "true_positives": int(tp),
        "true_negatives": int(tn),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "predicted_positive_count": int(tp + fp),
    }


def find_best_threshold_for_f1(y_true, probabilities):
    """
    Chooses the probability cutoff using validation data only.
    This is for Goal 1: classify every row as leak/no-leak.
    """
    results = []

    for threshold_int in range(1, 100):
        threshold = threshold_int / 100
        metrics = calculate_classification_metrics(
            y_true=y_true,
            probabilities=probabilities,
            threshold=threshold,
        )
        results.append(metrics)

    threshold_df = pd.DataFrame(results)
    threshold_df = threshold_df.sort_values("f1", ascending=False)

    best = threshold_df.iloc[0]

    print("\nBest validation threshold by F1")
    print("=" * 40)
    print(f"Threshold: {best['threshold']:.2f}")
    print(f"Precision: {best['precision']:.4f}")
    print(f"Recall:    {best['recall']:.4f}")
    print(f"F1:        {best['f1']:.4f}")
    print(f"Predicted positives: {int(best['predicted_positive_count']):,}")

    threshold_df.to_csv("threshold_tuning_results.csv", index=False)
    print("\nSaved threshold_tuning_results.csv")

    return float(best["threshold"]), threshold_df


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

    extra_metrics = calculate_classification_metrics(
        y_true=y,
        probabilities=probabilities,
        threshold=threshold,
    )

    print("\nLeak-class summary:")
    print(f"Precision: {extra_metrics['precision']:.4f}")
    print(f"Recall:    {extra_metrics['recall']:.4f}")
    print(f"F1:        {extra_metrics['f1']:.4f}")
    print(f"Predicted leak rows: {extra_metrics['predicted_positive_count']:,}")

    return probabilities, predictions, extra_metrics


def export_predictions(df, model, feature_cols, threshold):
    scoring_df = df[df["analysis_year"] == 2025].copy()

    if scoring_df.empty:
        print("\nNo 2025 rows found for scoring.")
        return

    X_score = scoring_df[feature_cols]

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

    print("\n2025 scoring summary:")
    print(
        scoring_df["predicted_leak_next_year"]
        .value_counts()
        .sort_index()
        .rename(index={0: "predicted_no_leak", 1: "predicted_leak"})
    )


def main():
    df = load_data()

    print(f"Loaded {len(df):,} rows")

    df["leaks_next_year"] = df["leaks_next_year"].astype(int)

    train_df = df[df["analysis_year"].between(2016, 2022)].copy()
    val_df = df[df["analysis_year"] == 2023].copy()
    test_df = df[df["analysis_year"] == 2024].copy()

    print(f"Train rows: {len(train_df):,}")
    print(f"Validation rows: {len(val_df):,}")
    print(f"Test rows: {len(test_df):,}")

    print("\nTarget distribution by split:")
    print("Train:")
    print(train_df["leaks_next_year"].value_counts().sort_index())
    print("Validation:")
    print(val_df["leaks_next_year"].value_counts().sort_index())
    print("Test:")
    print(test_df["leaks_next_year"].value_counts().sort_index())

    positives = train_df["leaks_next_year"].sum()
    negatives = len(train_df) - positives

    scale_pos_weight = negatives / positives if positives > 0 else 1

    print(f"\nTraining positives: {positives:,}")
    print(f"Training negatives: {negatives:,}")
    print(f"scale_pos_weight: {scale_pos_weight:.2f}")

    model, feature_cols = build_model(scale_pos_weight)

    X_train = train_df[feature_cols]
    y_train = train_df["leaks_next_year"]

    X_val = val_df[feature_cols]
    y_val = val_df["leaks_next_year"]

    X_test = test_df[feature_cols]
    y_test = test_df["leaks_next_year"]

    print("\nTraining XGBoost model...")
    model.fit(X_train, y_train)

    print("\nFinding best threshold using validation set...")
    val_probabilities = model.predict_proba(X_val)[:, 1]

    best_threshold, threshold_results = find_best_threshold_for_f1(
        y_true=y_val,
        probabilities=val_probabilities,
    )

    evaluate(
        model=model,
        X=X_val,
        y=y_val,
        label="Validation results with tuned threshold",
        threshold=best_threshold,
    )

    evaluate(
        model=model,
        X=X_test,
        y=y_test,
        label="Test results with tuned threshold",
        threshold=best_threshold,
    )

    joblib.dump(
        {
            "model": model,
            "feature_cols": feature_cols,
            "scale_pos_weight": scale_pos_weight,
            "best_threshold": best_threshold,
        },
        MODEL_PATH,
    )

    print(f"\nSaved model to {MODEL_PATH}")

    export_predictions(
        df=df,
        model=model,
        feature_cols=feature_cols,
        threshold=best_threshold,
    )


if __name__ == "__main__":
    main()

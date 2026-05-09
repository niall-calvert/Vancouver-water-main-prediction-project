import json
from itertools import product
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

MODEL_PATH = "catboost_leak_model_tuned.joblib"
PREDICTIONS_CSV = "pipe_leak_predictions_2025_catboost_tuned.csv"
PREDICTIONS_JSON = "docs/predictions_catboost_tuned.json"

TUNING_RESULTS_CSV = "catboost_hyperparameter_tuning_results.csv"
THRESHOLD_RESULTS_CSV = "catboost_tuned_threshold_results.csv"


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


def find_best_threshold(y_true, probabilities, output_csv=None):
    rows = []

    for i in range(1, 100):
        threshold = i / 100
        rows.append(calculate_metrics(y_true, probabilities, threshold))

    threshold_df = pd.DataFrame(rows).sort_values("f1", ascending=False)

    if output_csv:
        threshold_df.to_csv(output_csv, index=False)

    best = threshold_df.iloc[0]

    return float(best["threshold"]), best.to_dict(), threshold_df


def print_threshold_summary(best):
    print("\nBest validation threshold by F1")
    print("=" * 40)
    print(f"Threshold: {best['threshold']:.2f}")
    print(f"Precision: {best['precision']:.4f}")
    print(f"Recall:    {best['recall']:.4f}")
    print(f"F1:        {best['f1']:.4f}")
    print(f"Predicted positives: {int(best['predicted_positive_count']):,}")


def evaluate_probabilities(y, probabilities, label, threshold):
    predictions = (probabilities >= threshold).astype(int)

    print(f"\n{label}")
    print("=" * 40)
    print(f"Threshold: {threshold:.2f}")

    print("\nConfusion matrix:")
    print(confusion_matrix(y, predictions))

    print("\nClassification report:")
    print(classification_report(y, predictions, zero_division=0))

    roc_auc = roc_auc_score(y, probabilities)
    pr_auc = average_precision_score(y, probabilities)
    baseline_pr_auc = y.mean()
    lift = pr_auc / baseline_pr_auc if baseline_pr_auc > 0 else float("nan")

    print(f"ROC AUC: {roc_auc:.4f}")
    print(f"PR AUC: {pr_auc:.4f}")
    print(f"Baseline PR AUC: {baseline_pr_auc:.4f}")
    print(f"PR AUC lift over baseline: {lift:.2f}x")

    metrics = calculate_metrics(y, probabilities, threshold)

    print("\nLeak-class summary:")
    print(f"Precision: {metrics['precision']:.4f}")
    print(f"Recall:    {metrics['recall']:.4f}")
    print(f"F1:        {metrics['f1']:.4f}")
    print(f"Predicted leak rows: {metrics['predicted_positive_count']:,}")

    return metrics


def evaluate(model, X, y, label, threshold):
    probabilities = model.predict_proba(X)[:, 1]
    metrics = evaluate_probabilities(y, probabilities, label, threshold)
    return probabilities, metrics


def build_catboost_model(params, verbose=100):
    return CatBoostClassifier(
        iterations=params["iterations"],
        learning_rate=params["learning_rate"],
        depth=params["depth"],
        l2_leaf_reg=params["l2_leaf_reg"],
        min_data_in_leaf=params["min_data_in_leaf"],
        loss_function="Logloss",
        eval_metric="PRAUC",
        auto_class_weights="Balanced",
        bootstrap_type="MVS",
        random_seed=42,
        verbose=verbose,
        allow_writing_files=False,
    )


def tune_catboost(X_train, y_train, X_val, y_val, cat_feature_indices):
    """
    Small manual hyperparameter search.

    Selection rule:
      1. For each parameter combination, train on 2016–2022.
      2. Predict probabilities on 2023 validation data.
      3. Tune threshold on 2023 validation data.
      4. Pick the model with the best validation F1.
    """
    param_grid = {
        "iterations": [500, 700],
        "learning_rate": [0.03, 0.05],
        "depth": [4, 6],
        "l2_leaf_reg": [3, 10],
        "min_data_in_leaf": [20, 50],
    }

    combinations = list(product(
        param_grid["iterations"],
        param_grid["learning_rate"],
        param_grid["depth"],
        param_grid["l2_leaf_reg"],
        param_grid["min_data_in_leaf"],
    ))

    print(f"\nStarting CatBoost hyperparameter tuning...")
    print(f"Trying {len(combinations)} combinations.")

    results = []
    best_model = None
    best_params = None
    best_threshold = None
    best_threshold_metrics = None
    best_score = -1

    for i, (
        iterations,
        learning_rate,
        depth,
        l2_leaf_reg,
        min_data_in_leaf,
    ) in enumerate(combinations, start=1):

        params = {
            "iterations": iterations,
            "learning_rate": learning_rate,
            "depth": depth,
            "l2_leaf_reg": l2_leaf_reg,
            "min_data_in_leaf": min_data_in_leaf,
        }

        print("\n" + "-" * 60)
        print(f"Model {i}/{len(combinations)}")
        print(params)

        model = build_catboost_model(params, verbose=False)

        model.fit(
            X_train,
            y_train,
            cat_features=cat_feature_indices,
            eval_set=(X_val, y_val),
            use_best_model=True,
        )

        val_probabilities = model.predict_proba(X_val)[:, 1]

        threshold, threshold_metrics, _ = find_best_threshold(
            y_true=y_val,
            probabilities=val_probabilities,
        )

        roc_auc = roc_auc_score(y_val, val_probabilities)
        pr_auc = average_precision_score(y_val, val_probabilities)
        baseline_pr_auc = y_val.mean()
        pr_auc_lift = pr_auc / baseline_pr_auc if baseline_pr_auc > 0 else float("nan")

        row = {
            **params,
            "best_iteration": model.get_best_iteration(),
            "best_threshold": threshold,
            "validation_precision": threshold_metrics["precision"],
            "validation_recall": threshold_metrics["recall"],
            "validation_f1": threshold_metrics["f1"],
            "validation_predicted_positive_count": threshold_metrics["predicted_positive_count"],
            "validation_roc_auc": roc_auc,
            "validation_pr_auc": pr_auc,
            "validation_pr_auc_lift": pr_auc_lift,
        }

        results.append(row)

        print(
            f"Validation F1={row['validation_f1']:.4f}, "
            f"Precision={row['validation_precision']:.4f}, "
            f"Recall={row['validation_recall']:.4f}, "
            f"PR AUC={row['validation_pr_auc']:.4f}, "
            f"Threshold={row['best_threshold']:.2f}"
        )

        # Main tuning target for Goal 1: best validation F1.
        if row["validation_f1"] > best_score:
            best_score = row["validation_f1"]
            best_model = model
            best_params = params
            best_threshold = threshold
            best_threshold_metrics = threshold_metrics

    results_df = pd.DataFrame(results).sort_values(
        "validation_f1",
        ascending=False,
    )

    results_df.to_csv(TUNING_RESULTS_CSV, index=False)

    print("\n" + "=" * 60)
    print("Best hyperparameters by validation F1")
    print("=" * 60)
    print(best_params)
    print_threshold_summary(best_threshold_metrics)
    print(f"\nSaved {TUNING_RESULTS_CSV}")

    return best_model, best_params, best_threshold, results_df


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
    print(f"scale_pos_weight equivalent: {scale_pos_weight:.2f}")

    X_train = train_df[FEATURE_COLS]
    y_train = train_df["leaks_next_year"]

    X_val = val_df[FEATURE_COLS]
    y_val = val_df["leaks_next_year"]

    X_test = test_df[FEATURE_COLS]
    y_test = test_df["leaks_next_year"]

    cat_feature_indices = [
        FEATURE_COLS.index(col) for col in CATEGORICAL_FEATURES
    ]

    best_model, best_params, best_threshold, tuning_results = tune_catboost(
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        cat_feature_indices=cat_feature_indices,
    )

    # Save full threshold curve for the final selected model.
    final_val_probabilities = best_model.predict_proba(X_val)[:, 1]
    best_threshold, best_threshold_metrics, threshold_df = find_best_threshold(
        y_true=y_val,
        probabilities=final_val_probabilities,
        output_csv=THRESHOLD_RESULTS_CSV,
    )

    print(f"\nSaved {THRESHOLD_RESULTS_CSV}")

    evaluate(
        model=best_model,
        X=X_val,
        y=y_val,
        label="Validation results for tuned CatBoost",
        threshold=best_threshold,
    )

    evaluate(
        model=best_model,
        X=X_test,
        y=y_test,
        label="Test results for tuned CatBoost",
        threshold=best_threshold,
    )

    joblib.dump(
        {
            "model": best_model,
            "feature_cols": FEATURE_COLS,
            "categorical_features": CATEGORICAL_FEATURES,
            "best_threshold": best_threshold,
            "best_params": best_params,
            "scale_pos_weight_equivalent": scale_pos_weight,
        },
        MODEL_PATH,
    )

    print(f"\nSaved model to {MODEL_PATH}")

    export_predictions(df, best_model, best_threshold)


if __name__ == "__main__":
    main()

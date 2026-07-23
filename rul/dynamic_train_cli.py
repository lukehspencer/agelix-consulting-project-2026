"""
Train a dynamic RUL model on historical run-to-failure data.

Usage:
  python -m rul.dynamic_train_cli --file <path_to_excel>
  python -m rul.dynamic_train_cli --file data/raw/uploads/KSB_Full_Upload.xlsx

The trained model is saved to rul/models/<asset_type>.pkl
True_RUL_Days column is required in the training file.

This is the only way to train a new dynamic RUL model from scratch. It is
never called from the API or frontend -- the user-facing upload flow only
predicts against models trained by this script.
"""
import argparse

from data.schema_inferrer import infer_criteria_config
from data.upload_schema import UploadValidationError, validate_upload
from rag.knowledge_base import store_criteria_config
from rag.retriever import retrieve_for_schema_inference
from rul import model_registry
from rul.dynamic_train import train_dynamic_model


def main():
    parser = argparse.ArgumentParser(
        description="Train a dynamic RUL model on historical run-to-failure data."
    )
    parser.add_argument("--file", required=True, help="Path to the Excel training file")
    parser.add_argument("--config", default=None,
        help="Path to pre-built CriteriaConfig JSON. Skips Claude inference.")
    args = parser.parse_args()

    file_path = args.file

    print(f"Validating '{file_path}'...")
    try:
        schema_summary = validate_upload(file_path, require_rul_column=True)
    except UploadValidationError as exc:
        raise SystemExit(f"Validation failed: {exc}")

    if not schema_summary.get("has_rul_column"):
        raise SystemExit(
            "Training requires a True_RUL_Days (or similarly named) column in the "
            "telemetry sheet. None was found."
        )

    if args.config:
        import json
        with open(args.config) as f:
            criteria_config = json.load(f)
        print(f"Using pre-built config from {args.config}")
    else:
        print("Inferring AHP criteria config via Claude...")
        retrieved_context = retrieve_for_schema_inference(schema_summary)
        try:
            criteria_config = infer_criteria_config(
                schema_summary, retrieved_context, file_path=file_path,
            )
        except RuntimeError as exc:
            raise SystemExit(f"Criteria inference failed: {exc}")

    try:
        store_criteria_config(criteria_config, criteria_config.get("asset_type", "unknown"))
    except Exception:
        pass

    asset_type = criteria_config.get("asset_type", "unknown_asset")
    model_output_path = model_registry.model_path_for_asset_type(asset_type)

    print(f"Training dynamic RUL model for '{asset_type}'...")
    result = train_dynamic_model(
        file_path, schema_summary, criteria_config,
        model_output_path=model_output_path,
    )

    print("\nTraining complete.")
    print(f"  Asset type:   {asset_type}")
    print(f"  Samples:      {result['n_train_samples']} train / {result['n_test_samples']} test")
    print(f"  Train RMSE:   {result['train_rmse']:.4f} years")
    print(f"  Test RMSE:    {result['test_rmse']:.4f} years")
    print(f"  Model saved:  {result['model_path']}")


if __name__ == "__main__":
    main()

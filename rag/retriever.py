from rag.knowledge_base import query


def retrieve_for_schema_inference(schema_summary: dict) -> dict:
    sensor_names = ", ".join(schema_summary.get("sensor_columns", []))
    asset_ids = schema_summary.get("asset_ids", [])
    asset_hint = str(asset_ids[:3]) if asset_ids else "unknown"

    try:
        standards_chunks = query(
            f"engineering standards operating limits thresholds for sensors: {sensor_names}",
            n_results=5,
            doc_type="manual",
        )
        similar_configs = query(
            f"AHP criteria config for asset type with sensors {sensor_names} assets {asset_hint}",
            n_results=3,
            doc_type="criteria_config",
        )
        failure_case_chunks = query(
            f"failure cases failure modes for asset with sensors: {sensor_names}",
            n_results=5,
            doc_type="failure_case",
        )
    except RuntimeError:
        return {
            "standards_chunks": [],
            "similar_configs": [],
            "failure_case_chunks": [],
            "retrieval_available": False,
        }

    return {
        "standards_chunks": standards_chunks,
        "similar_configs": similar_configs,
        "failure_case_chunks": failure_case_chunks,
        "retrieval_available": True,
    }


def retrieve_for_explanation(
    asset_snapshot: dict,
    criteria_config: dict,
    risk_factor: float,
) -> dict:
    asset_type = criteria_config.get("asset_type", "unknown")
    failure_modes = criteria_config.get("failure_modes", [])
    fm_text = ", ".join(failure_modes)

    try:
        failure_precedents = query(
            f"failure precedent for {asset_type} with failure modes: {fm_text} "
            f"risk factor {risk_factor:.1f}",
            n_results=3,
            doc_type="failure_case",
        )
        maintenance_guidance = query(
            f"maintenance standards recommendations for {asset_type} "
            f"preventive maintenance intervals thresholds",
            n_results=3,
            doc_type="manual",
        )
    except RuntimeError:
        return {
            "failure_precedents": [],
            "maintenance_guidance": [],
            "retrieval_available": False,
        }

    return {
        "failure_precedents": failure_precedents,
        "maintenance_guidance": maintenance_guidance,
        "retrieval_available": True,
    }

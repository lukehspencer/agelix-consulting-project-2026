def resolve(row: dict, role: str, criteria_config: dict,
            default=None, required: bool = False):
    col = criteria_config["column_roles"].get(role)
    if col is None:
        if required:
            raise KeyError(
                f"Role '{role}' not found in column_roles. "
                f"Available roles: {sorted(criteria_config['column_roles'].keys())}"
            )
        return default

    if col not in row:
        if required:
            raise KeyError(
                f"Column '{col}' (role: '{role}') not found in row. "
                f"Available keys: {sorted(row.keys())}"
            )
        return default

    return row[col]


def resolve_sensor(row: dict, column_name: str, default=None,
                   required: bool = False):
    if column_name not in row:
        if required:
            raise KeyError(
                f"Column '{column_name}' (sensor) not found in row. "
                f"Available keys: {sorted(row.keys())}"
            )
        return default

    return row[column_name]


def is_failure_event(row: dict, criteria_config: dict) -> bool:
    val = resolve(row, "log_event_type", criteria_config)
    if val is None:
        return False

    val_normalized = str(val).strip().lower()
    for fev in criteria_config.get("failure_event_values", []):
        if str(fev).strip().lower() == val_normalized:
            return True
    return False


def get_sensor_columns(criteria_config: dict) -> list[str]:
    seen = set()
    result = []

    for crit in criteria_config.get("criteria", []):
        if crit.get("manual_input"):
            continue

        primary = crit.get("primary_column")
        if primary and primary not in seen:
            seen.add(primary)
            result.append(primary)

        for sc in crit.get("secondary_columns", []):
            if sc not in seen:
                seen.add(sc)
                result.append(sc)

        for pen in crit.get("penalties", []):
            pc = pen.get("column")
            if pc and pc not in seen:
                seen.add(pc)
                result.append(pc)

    return result

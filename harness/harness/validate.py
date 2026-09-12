"""Schema validation: accept nothing on the seat's word.

Rows validate against columns, enums, row counts, and mandatory flag fields.
Artifacts validate against required keys. Errors come back as short named
strings (the retry protocol sends them to the seat verbatim), capped so a
hundred-row failure does not become its own essay.
"""

MAX_ERRORS = 12


def validate_rows(rows, spec) -> list:
    errors = []
    if not isinstance(rows, list):
        return [f"expected a JSON array of objects, got {type(rows).__name__}"]
    if spec.row_count is not None and len(rows) != spec.row_count:
        errors.append(f"row count {len(rows)} != required {spec.row_count}")
    required = list(spec.columns) + [f for f in spec.flag_fields if f not in spec.columns]
    for i, row in enumerate(rows):
        if len(errors) >= MAX_ERRORS:
            errors.append("further errors suppressed")
            break
        if not isinstance(row, dict):
            errors.append(f"row {i}: not an object")
            continue
        missing = [c for c in required if c not in row]
        if missing:
            errors.append(f"row {i}: missing keys {missing}")
        for col, allowed in spec.enums.items():
            if col in row and row[col] not in allowed and row[col] not in ("", None):
                errors.append(f"row {i}: {col}={row[col]!r} not in {allowed}")
    return errors


def validate_artifact(obj, spec) -> list:
    if not isinstance(obj, dict):
        return [f"expected a JSON object, got {type(obj).__name__}"]
    missing = [k for k in spec.artifact_keys if k not in obj]
    return [f"missing keys {missing}"] if missing else []


def stamp_escalation(rows, rule) -> int:
    """Escalation as data. Stamps row['escalate'] per the declarative rule;
    returns how many rows escalated."""
    if not rule:
        return 0
    comp_fields = rule.get("composite_fields", [])
    comp_gte = rule.get("composite_gte")
    claim_fields = rule.get("claim_fields", [])
    claim_values = set(rule.get("claim_values", []))
    n = 0
    for row in rows:
        esc = False
        if comp_fields and comp_gte is not None:
            try:
                total = sum(float(row.get(f, 0) or 0) for f in comp_fields)
                esc = total >= comp_gte
            except (TypeError, ValueError):
                pass
        if not esc and claim_fields and claim_values:
            esc = any(row.get(f) in claim_values for f in claim_fields)
        row["escalate"] = bool(esc)
        n += esc
    return n

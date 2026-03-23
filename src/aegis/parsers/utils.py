from decimal import Decimal, InvalidOperation


def clean_amount(raw: str) -> Decimal:
    """
    Cleans a raw Argentine-formatted amount string and returns a Decimal.
    - Removes `.` as thousands separator
    - Detects trailing `-` (e.g. `35.771,17-`) and multiplies by `-1`
    - Replaces `,` with `.`
    - Casts to `Decimal`
    - Raises `ValueError` on un-parseable input
    """
    cleaned = raw.strip()
    if not cleaned:
        raise ValueError(f"Cannot parse amount from empty/non-numeric value: {raw!r}")

    is_negative = False
    if cleaned.endswith("-"):
        is_negative = True
        cleaned = cleaned[:-1].strip()
    elif cleaned.startswith("-"):
        is_negative = True
        cleaned = cleaned[1:].strip()

    cleaned = cleaned.replace(".", "")
    cleaned = cleaned.replace(",", ".")

    try:
        val = Decimal(cleaned)
        if is_negative:
            val *= Decimal("-1")
        return val
    except InvalidOperation as exc:
        raise ValueError(
            f"Cannot convert {raw!r} (cleaned: {cleaned!r}) to Decimal"
        ) from exc

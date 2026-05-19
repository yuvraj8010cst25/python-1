from __future__ import annotations


def clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


def format_inr(value: float) -> str:
    rounded = max(0, round(value))
    digits = str(rounded)
    if len(digits) <= 3:
        formatted = digits
    else:
        last_three = digits[-3:]
        rest = digits[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted = ",".join(groups + [last_three])
    return f"₹{formatted}"


def format_compact_inr(value: float) -> str:
    amount = max(0, value)
    if amount >= 10_000_000:
        return f"₹{amount / 10_000_000:.2f} Cr"
    if amount >= 100_000:
        return f"₹{amount / 100_000:.2f} L"
    return format_inr(amount)

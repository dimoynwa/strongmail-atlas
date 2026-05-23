"""Dynamic content rule engine for parsing and evaluating DSL rules from data/dynamic_content."""

import re
from pathlib import Path
from typing import Any

from strongmail.placeholder_resolution.key_normalization import (
    canonical_placeholder_key,
    parameters_canonical_copy,
)

# JSON ``rule_ast`` schema version for consumers (e.g. PostgreSQL jsonb).
RULE_AST_SCHEMA_VERSION = 1
RULE_AST_KIND = "strongmail_dynamic_content_rule"

# Operators (case-insensitive) and their evaluation logic
OPERATORS = {
    "is equal to": lambda a, b: _str(a).lower() == _str(b).lower(),
    "is not equal to": lambda a, b: _str(a).lower() != _str(b).lower(),
    "contains": lambda a, b: _str(b).lower() in _str(a).lower(),
    "does not contain": lambda a, b: _str(b).lower() not in _str(a).lower(),
    "is greater than": lambda a, b: _numeric_cmp(a, b) > 0,
    "is greater than or equal to": lambda a, b: _numeric_cmp(a, b) >= 0,
    "is less than": lambda a, b: _numeric_cmp(a, b) < 0,
    "is less than or equal to": lambda a, b: _numeric_cmp(a, b) <= 0,
    "is null": lambda a, _: a is None or a == "" or (isinstance(a, str) and a.strip() == ""),
    "is not null": lambda a, _: not (a is None or a == "" or (isinstance(a, str) and a.strip() == "")),
    "is one of": lambda a, b: _str(a).lower() in [_str(x).lower() for x in _as_list(b)],
    "is not one of": lambda a, b: _str(a).lower() not in [_str(x).lower() for x in _as_list(b)],
}


def _str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _numeric_cmp(a: Any, b: Any) -> int:
    """Compare as numbers if possible, else as strings. Return -1, 0, or 1."""
    try:
        na, nb = float(_str(a)), float(_str(b))
        return (na > nb) - (na < nb)
    except (ValueError, TypeError):
        sa, sb = _str(a), _str(b)
        return (sa > sb) - (sa < sb)


def _as_list(val: Any) -> list:
    """Parse value as list for 'is one of' / 'is not one of'. Supports (A, B, C) or comma-separated A, B, C."""
    s = _str(val)
    if not s:
        return []
    # Strip optional outer parentheses
    if s[0] == "(" and s[-1] == ")":
        s = s[1:-1].strip()
    return [x.strip() for x in s.split(",") if x.strip()]


def _extract_variable(var_expr: str) -> str:
    """Extract variable name from dot notation. Use last segment, uppercase."""
    parts = var_expr.strip().split(".")
    if not parts:
        return ""
    return parts[-1].strip().upper()


def _resolve_value(val: str, params: dict[str, str]) -> str:
    """Resolve value: if ##key##, look up key in params (``params`` keys are canonical); else literal."""
    m = re.match(r"^##([A-Za-z0-9_.]+)##$", val.strip())
    if m:
        key = canonical_placeholder_key(m.group(1))
        return params.get(key, "")
    return val.strip()


def _normalize_return_value(raw: str) -> str:
    """
    Normalize return value per spec:
    1. Replace #### with ##
    2. Remove leading \\
    3. If result matches ^[A-Z_]+$, return SM_RULE_<VALUE> (key for recursive resolution)
    4. Otherwise return as lookup key (e.g. ##X.Y## -> X.Y)
    """
    s = raw.strip()
    s = s.replace("####", "##")
    # Remove leading backslash (spec: "Remove leading \\")
    if s.startswith("\\"):
        s = s[1:]
    # Plain value (no ##) matching ^[A-Z_]+$ -> SM_RULE_<VALUE>
    if re.match(r"^[A-Z_]+$", s):
        return f"SM_RULE_{s}"
    if s.startswith("##") and s.endswith("##"):
        inner = s[2:-2].strip()
        if inner.startswith("\\"):
            inner = inner[1:]
        if re.match(r"^[A-Z_]+$", inner):
            return f"SM_RULE_{inner}"
        return inner
    return s


def _parse_condition(cond_str: str) -> list[tuple[str, str, str]]:
    """
    Parse condition string into list of (var_expr, operator, value).
    Handles Or/And combinations and nested parentheses.
    """
    cond_str = cond_str.strip()
    conditions: list[tuple[str, str, str]] = []
    # Split by Or/And (case-insensitive), respecting parentheses
    parts = _split_by_or_and(cond_str)
    for part in parts:
        part = part.strip()
        if not part or part == "(" or part == ")":
            continue
        # Remove outer parentheses
        while part.startswith("(") and part.endswith(")"):
            part = part[1:-1].strip()
        # Match: <var> <operator> <value>
        for op_name in sorted(OPERATORS.keys(), key=len, reverse=True):
            op_pattern = re.escape(op_name)
            m = re.search(r"^(.+?)\s+" + op_pattern + r"\s+(.+)$", part, re.IGNORECASE | re.DOTALL)
            if m:
                var_expr = m.group(1).strip()
                value = m.group(2).strip()
                conditions.append((var_expr, op_name.lower(), value))
                break
    return conditions


def _split_by_or_and(s: str) -> list[str]:
    """Split by Or/And while respecting parentheses. Returns list of condition strings.
    Skips Or/And when part of an identifier (e.g. param_cust_brand contains "and").
    """
    result: list[str] = []
    depth = 0
    current: list[str] = []
    i = 0
    n = len(s)
    or_and_pattern = re.compile(r"\b(?:Or|And)\b", re.IGNORECASE)
    while i < n:
        if depth == 0:
            m = or_and_pattern.match(s[i:])
            if m:
                # Only split if Or/And is not part of identifier (e.g. param_cust_brand)
                if i == 0 or s[i - 1] not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_":
                    result.append("".join(current).strip())
                    current = []
                    i += len(m.group())
                    continue
        c = s[i]
        if c == "(":
            depth += 1
            current.append(c)
        elif c == ")":
            depth -= 1
            current.append(c)
        else:
            current.append(c)
        i += 1
    if current:
        result.append("".join(current).strip())
    return result


def _evaluate_condition(conditions: list[tuple[str, str, str]], params: dict[str, str]) -> bool:
    """Evaluate conditions combined with Or (any true) or And (all true). Default Or."""
    if not conditions:
        return False
    # Determine combiner from original structure - for simplicity, we treat multiple
    # conditions from _split_by_or_and as Or. A single condition with And would
    # need different handling. Per spec: "Be combined using Or, Possibly include And".
    # We'll evaluate each condition and Or them together for now.
    for var_expr, op_name, value in conditions:
        var_key = _extract_variable(var_expr)
        actual_val = params.get(var_key, "")
        resolved_rhs = _resolve_value(value, params)
        op_fn = OPERATORS.get(op_name.lower())
        if op_fn:
            if op_name.lower() in ("is null", "is not null"):
                if op_fn(actual_val if actual_val != "" else None, None):
                    return True
            elif op_name.lower() in ("is one of", "is not one of"):
                if op_fn(actual_val, value):
                    return True
            else:
                if op_fn(actual_val, resolved_rhs):
                    return True
    return False


def _extract_paren_content(s: str, start: int) -> tuple[str, int]:
    """Extract balanced (...) content starting at start. Returns (content, end_pos)."""
    if start >= len(s) or s[start] != "(":
        return ("", start)
    depth = 1
    i = start + 1
    while i < len(s) and depth > 0:
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
        i += 1
    return (s[start + 1 : i - 1], i)


def _parse_rule(content: str) -> tuple[list[tuple[str, str, str]], str, str | None]:
    """Parse rule content. Returns (conditions, then_value, else_value or None)."""
    content = content.strip()
    if not content.lower().startswith("if"):
        return ([], "", None)
    idx = content.find("(")
    if idx < 0:
        return ([], "", None)
    cond_str, end = _extract_paren_content(content, idx)
    rest = content[end:].strip()
    if not rest.lower().startswith("then"):
        return ([], "", None)
    rest = rest[4:].strip()  # skip "then"
    # Split then/else by " else " (last occurrence)
    else_match = re.search(r"\s+else\s+(.+)$", rest, re.IGNORECASE | re.DOTALL)
    if else_match:
        then_val = rest[: else_match.start()].strip()
        else_val = else_match.group(1).strip()
    else:
        then_val = rest
        else_val = None
    conditions = _parse_condition(cond_str)
    return conditions, then_val, else_val


def parse_rule_to_ast(content: str) -> dict[str, Any]:
    """
    Parse rule text into a JSON-serializable dict for storage (e.g. ``rule_ast``).

    StrongMail rules use phrases like ``is equal to``; they are not Python expressions (asteval and
    similar tools target Python: https://github.com/lmfit/asteval/blob/master/README.rst).
    """
    raw = content or ""
    stripped = raw.strip()
    conditions, then_val, else_val = _parse_rule(raw)
    valid = bool(stripped) and stripped.lower().startswith("if") and bool(conditions)
    clauses: list[dict[str, str]] = []
    for var_expr, op_name, value in conditions:
        clauses.append(
            {
                "variable_expr": var_expr,
                "variable_key": _extract_variable(var_expr),
                "operator": op_name,
                "value": value,
            }
        )
    return {
        "schema_version": RULE_AST_SCHEMA_VERSION,
        "kind": RULE_AST_KIND,
        "valid": valid,
        "condition": {"combiner": "or", "clauses": clauses},
        "then": then_val,
        "else": else_val,
    }


def get_dynamic_content_dir() -> Path:
    """Return path to ``data/dynamic_content`` under the paysafe-email-tone-of-voice project root."""
    return Path(__file__).resolve().parents[2] / "data" / "dynamic_content"


def load_rule(rule_name: str) -> str | None:
    """Load rule file content. rule_name is the part after SM_RULE_ (e.g. AMO_BRAND_LOGO)."""
    base = get_dynamic_content_dir()
    candidates = [
        base / f"{rule_name}_rule.html",
        base / f"SM_RULE_{rule_name}_rule.html",
    ]
    for p in candidates:
        if p.exists():
            return p.read_text(encoding="utf-8")
    return None


def evaluate_rule_from_text(content: str, params: dict[str, str]) -> str:
    """
    Parse and evaluate dynamic content rule text (e.g. from ``dynamic_content_details.rule_text``).
    Returns the normalized result (a key for lookup or a template fragment).
    """
    if not (content or "").strip():
        return ""
    conditions, then_val, else_val = _parse_rule(content)
    params_c = parameters_canonical_copy(params)
    condition_met = _evaluate_condition(conditions, params_c)
    raw_result = then_val if condition_met else (else_val if else_val is not None else "")
    return _normalize_return_value(raw_result)


def evaluate_rule(rule_name: str, params: dict[str, str]) -> str:
    """
    Load, parse, and evaluate a dynamic content rule from ``data/dynamic_content`` (optional).
    """
    content = load_rule(rule_name)
    if not content:
        return ""
    return evaluate_rule_from_text(content, params)

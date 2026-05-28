"""
Parse StrongMail dynamic content rule text into JSON for ``rule_ast``.

Keep parsing logic aligned with:
``strongmail-email-resolution-system/src/email_resolution/services/dynamic_content_rule_engine.py``

StrongMail rules use natural-language operators (e.g. ``is equal to``), not Python. Tools like
asteval (https://github.com/lmfit/asteval/blob/master/README.rst) target Python expressions only.
"""

from __future__ import annotations

import re
from typing import Any

RULE_AST_SCHEMA_VERSION = 1
RULE_AST_KIND = "strongmail_dynamic_content_rule"

# Operator names only (same set as dynamic_content_rule_engine.OPERATORS); longest match first.
_OPERATOR_NAMES = sorted(
    (
        "is equal to",
        "is not equal to",
        "contains",
        "does not contain",
        "is greater than or equal to",
        "is less than or equal to",
        "is greater than",
        "is less than",
        "is not one of",
        "is one of",
        "is not null",
        "is null",
    ),
    key=len,
    reverse=True,
)


def _extract_variable(var_expr: str) -> str:
    parts = var_expr.strip().split(".")
    if not parts:
        return ""
    return parts[-1].strip().upper()


def _split_by_or_and(s: str) -> list[str]:
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


def _parse_condition(cond_str: str) -> list[tuple[str, str, str]]:
    cond_str = cond_str.strip()
    conditions: list[tuple[str, str, str]] = []
    parts = _split_by_or_and(cond_str)
    for part in parts:
        part = part.strip()
        if not part or part == "(" or part == ")":
            continue
        while part.startswith("(") and part.endswith(")"):
            part = part[1:-1].strip()
        for op_name in _OPERATOR_NAMES:
            op_pattern = re.escape(op_name)
            if op_name in ("is null", "is not null"):
                m = re.search(r"^(.+?)\s+" + op_pattern + r"\s*$", part, re.IGNORECASE | re.DOTALL)
                if m:
                    conditions.append((m.group(1).strip(), op_name, ""))
                    break
            else:
                m = re.search(r"^(.+?)\s+" + op_pattern + r"\s+(.+)$", part, re.IGNORECASE | re.DOTALL)
                if m:
                    var_expr = m.group(1).strip()
                    value = m.group(2).strip()
                    conditions.append((var_expr, op_name, value))
                    break
    return conditions


def _extract_paren_content(s: str, start: int) -> tuple[str, int]:
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
    rest = rest[4:].strip()
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

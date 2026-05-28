import re
import asyncpg
from typing import Any

from shared.resolution.resolver import ReasonCode
from shared.resolution.rule_parser import parse_rule_to_ast


def _normalize_return_value(value: str | None) -> str | None:
    if value is None:
        return None

    val = value.replace("####", "##")

    if val.startswith("\\"):
        val = val[1:]

    if re.match(r"^[A-Z_]+$", val):
        return f"SM_RULE_{val}"

    if val.startswith("##") and val.endswith("##"):
        inner = val[2:-2].strip()
        if inner.startswith("\\"):
            inner = inner[1:]
        if re.match(r"^[A-Z_]+$", inner):
            return f"SM_RULE_{inner}"
        return inner

    return val


def _numeric_cmp(a: str, b: str) -> int:
    try:
        na, nb = float(a.strip()), float(b.strip())
        return (na > nb) - (na < nb)
    except (ValueError, TypeError):
        sa, sb = a.strip(), b.strip()
        return (sa > sb) - (sa < sb)


def _as_list(val: str) -> list[str]:
    s = val.strip()
    if not s:
        return []
    if s[0] == "(" and s[-1] == ")":
        s = s[1:-1].strip()
    return [x.strip() for x in s.split(",") if x.strip()]


def _evaluate_condition(condition: dict[str, Any], context: dict[str, str]) -> bool:
    combiner = condition.get("combiner", "or").lower()
    clauses = condition.get("clauses", [])

    if not clauses:
        return True

    results = []
    for clause in clauses:
        var_key = clause.get("variable_key", "").upper()
        op = clause.get("operator", "").lower()
        target_val = clause.get("value", "")

        ctx_val = context.get(var_key, "")

        res = False
        if op == "is equal to":
            res = ctx_val.lower() == target_val.lower()
        elif op == "is not equal to":
            res = ctx_val.lower() != target_val.lower()
        elif op == "contains":
            res = target_val.lower() in ctx_val.lower()
        elif op == "does not contain":
            res = target_val.lower() not in ctx_val.lower()
        elif op == "is null":
            res = ctx_val == ""
        elif op == "is not null":
            res = ctx_val != ""
        elif op == "is one of":
            items = [x.lower() for x in _as_list(target_val)]
            res = ctx_val.lower() in items
        elif op == "is not one of":
            items = [x.lower() for x in _as_list(target_val)]
            res = ctx_val.lower() not in items
        elif op == "is greater than":
            res = _numeric_cmp(ctx_val, target_val) > 0
        elif op == "is greater than or equal to":
            res = _numeric_cmp(ctx_val, target_val) >= 0
        elif op == "is less than":
            res = _numeric_cmp(ctx_val, target_val) < 0
        elif op == "is less than or equal to":
            res = _numeric_cmp(ctx_val, target_val) <= 0
        results.append(res)

    if combiner == "and":
        return all(results)
    return any(results)


async def evaluate_sm_rule(
    pool: asyncpg.Pool,
    rule_name: str,
    context: dict[str, str],
) -> str | ReasonCode:
    """Evaluate an SM_RULE against the runtime context.

    rule_name should be the full key, e.g., 'SM_RULE_BRAND_COLOR' or 'BRAND_COLOR'.
    """
    full_key = rule_name if rule_name.startswith("SM_RULE_") else f"SM_RULE_{rule_name}"
    stripped_name = full_key[8:]

    query = """
        SELECT dcd.rule_text
        FROM dynamic_content d
        JOIN dynamic_content_details dcd ON dcd.dynamic_content_id = d.id
        WHERE d.name = $1 OR d.name = $2
        ORDER BY (d.name = $1) DESC
        LIMIT 1
    """

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, stripped_name, full_key)

    if row is None:
        return ReasonCode.MISSING_KEY

    rule_text = row["rule_text"]
    if rule_text is None or not str(rule_text).strip():
        return ReasonCode.INVALID_RULE

    ast = parse_rule_to_ast(str(rule_text))

    if not ast.get("valid", False):
        return ReasonCode.INVALID_RULE

    condition = ast.get("condition", {})
    is_true = _evaluate_condition(condition, context)

    if is_true:
        branch_val = ast.get("then")
    else:
        branch_val = ast.get("else")

    if branch_val is None:
        return ""

    return _normalize_return_value(branch_val) or ""

import json
import re
import asyncpg
from typing import Any

from shared.resolution.resolver import ReasonCode

def _normalize_return_value(value: str | None) -> str | None:
    if value is None:
        return None
    
    # 1. Replace `####` with `##`
    val = value.replace("####", "##")
    
    # 2. Strip leading `\`
    if val.startswith("\\"):
        val = val[1:]
        
    # 3. If matches `^[A-Z_]+$` → return `SM_RULE_{value}`
    if re.match(r"^[A-Z_]+$", val):
        return f"SM_RULE_{val}"
        
    # 4. If wrapped in `##...##` → extract inner key for graph lookup
    if val.startswith("##") and val.endswith("##"):
        inner = val[2:-2].strip()
        if inner.startswith("\\"):
            inner = inner[1:]
        if re.match(r"^[A-Z_]+$", inner):
            return f"SM_RULE_{inner}"
        return inner
        
    # 5. Otherwise → return as literal inline string
    return val

def _evaluate_condition(condition: dict[str, Any], context: dict[str, str]) -> bool:
    combiner = condition.get("combiner", "or").lower()
    clauses = condition.get("clauses", [])
    
    if not clauses:
        return True # Default true if no clauses? Assume true.
        
    results = []
    for clause in clauses:
        var_key = clause.get("variable_key", "").upper()
        op = clause.get("operator", "").lower()
        target_val = clause.get("value", "")
        
        ctx_val = context.get(var_key, "")
        
        # Supported operators: "is equal to", "is not equal to", "contains", "does not contain", 
        # "is greater than", "is greater than or equal to", "is less than", "is less than or equal to", 
        # "is null", "is not null", "is one of", "is not one of"
        res = False
        if op == "is equal to":
            res = (ctx_val.lower() == target_val.lower())
        elif op == "is not equal to":
            res = (ctx_val.lower() != target_val.lower())
        elif op == "contains":
            res = (target_val.lower() in ctx_val.lower())
        elif op == "does not contain":
            res = (target_val.lower() not in ctx_val.lower())
        elif op == "is null":
            res = (ctx_val == "")
        elif op == "is not null":
            res = (ctx_val != "")
        elif op == "is one of":
            # Assume target_val is a comma-separated list or similar
            items = [x.strip().lower() for x in target_val.replace("(", "").replace(")", "").split(",")]
            res = (ctx_val.lower() in items)
        elif op == "is not one of":
            items = [x.strip().lower() for x in target_val.replace("(", "").replace(")", "").split(",")]
            res = (ctx_val.lower() not in items)
        # Note: numerical comparisons omitted for brevity unless needed; 
        # normally string-based or cast to float
        results.append(res)
        
    if combiner == "and":
        return all(results)
    else:
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
    stripped_name = full_key[8:] # strip 'SM_RULE_'
    
    query = """
        SELECT dcd.rule_ast
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
        
    ast_json = row["rule_ast"]
    if ast_json is None:
        return ReasonCode.INVALID_RULE
        
    if isinstance(ast_json, str):
        try:
            ast = json.loads(ast_json)
        except json.JSONDecodeError:
            return ReasonCode.INVALID_RULE
    else:
        # asyncpg might return parsed dict if JSON type
        ast = ast_json
        
    if not ast.get("valid", True):
        return ReasonCode.INVALID_RULE
        
    condition = ast.get("condition", {})
    is_true = _evaluate_condition(condition, context)
    
    if is_true:
        branch_val = ast.get("then")
    else:
        branch_val = ast.get("else")
        
    if branch_val is None:
        # If branch is None, treat as empty literal string or missing key?
        # A None branch in a rule means empty string literal
        return ""
        
    return _normalize_return_value(branch_val) or ""

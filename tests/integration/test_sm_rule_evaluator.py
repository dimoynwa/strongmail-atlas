import json

import pytest

from shared.resolution.resolver import ReasonCode
from shared.resolution.sm_rule_evaluator import (
    _evaluate_condition,
    _normalize_return_value,
    evaluate_sm_rule,
)

def test_normalize_return_value():
    assert _normalize_return_value("###255F11##") == "#255F11" 
    
    assert _normalize_return_value("\\#255F11") == "#255F11"
    assert _normalize_return_value("BRAND_COLOR_BUSINESS_WALLET") == "SM_RULE_BRAND_COLOR_BUSINESS_WALLET"
    assert _normalize_return_value("##SOME.KEY##") == "SOME.KEY"
    assert _normalize_return_value("Some random literal") == "Some random literal"

def test_evaluate_condition():
    context = {"PARAM_CUST_BRAND": "NETELLER"}
    
    cond_or = {
        "combiner": "or",
        "clauses": [
            {
                "variable_key": "PARAM_CUST_BRAND",
                "operator": "is equal to",
                "value": "Neteller"
            }
        ]
    }
    assert _evaluate_condition(cond_or, context) == True
    
    cond_and = {
        "combiner": "and",
        "clauses": [
            {
                "variable_key": "PARAM_CUST_BRAND",
                "operator": "is not equal to",
                "value": "Skrill"
            }
        ]
    }
    assert _evaluate_condition(cond_and, context) == True
    
    cond_contains = {
        "combiner": "or",
        "clauses": [
            {
                "variable_key": "PARAM_CUST_BRAND",
                "operator": "contains",
                "value": "net"
            }
        ]
    }
    assert _evaluate_condition(cond_contains, context) == True

    cond_one_of = {
        "combiner": "or",
        "clauses": [
            {
                "variable_key": "PARAM_CUST_BRAND",
                "operator": "is one of",
                "value": "(Skrill, Neteller)"
            }
        ]
    }
    assert _evaluate_condition(cond_one_of, context) is True

    cond_numeric = {
        "combiner": "or",
        "clauses": [
            {
                "variable_key": "COUNT",
                "operator": "is greater than",
                "value": "5",
            }
        ],
    }
    assert _evaluate_condition(cond_numeric, {"COUNT": "10"}) is True
    assert _evaluate_condition(cond_numeric, {"COUNT": "3"}) is False


@pytest.mark.asyncio
async def test_evaluate_sm_rule_from_rule_text(db_pool):
    rule_text = (
        "If (PARAM_CUST_BRAND is equal to Neteller) Then ###255F11## "
        "Else BRAND_COLOR_BUSINESS_WALLET"
    )
    wrong_ast = {
        "schema_version": 1,
        "kind": "strongmail_dynamic_content_rule",
        "valid": True,
        "condition": {
            "combiner": "or",
            "clauses": [
                {
                    "variable_key": "PARAM_CUST_BRAND",
                    "operator": "is equal to",
                    "value": "Skrill",
                }
            ],
        },
        "then": "WRONG",
        "else": None,
    }
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM dynamic_content_details WHERE dynamic_content_id = 'dc-test'")
        await conn.execute("DELETE FROM dynamic_content WHERE id = 'dc-test'")
        await conn.execute(
            "INSERT INTO dynamic_content (id, name) VALUES ('dc-test', 'BRAND_COLOR')"
        )
        await conn.execute(
            """
            INSERT INTO dynamic_content_details (dynamic_content_id, rule_ast, rule_text)
            VALUES ('dc-test', $1::json, $2)
            """,
            json.dumps(wrong_ast),
            rule_text,
        )

    result = await evaluate_sm_rule(db_pool, "SM_RULE_BRAND_COLOR", {"PARAM_CUST_BRAND": "NETELLER"})
    assert result == "#255F11"

    missing = await evaluate_sm_rule(db_pool, "SM_RULE_DOES_NOT_EXIST", {"PARAM_CUST_BRAND": "X"})
    assert missing == ReasonCode.MISSING_KEY

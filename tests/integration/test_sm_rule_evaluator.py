import pytest
from shared.resolution.sm_rule_evaluator import _normalize_return_value, _evaluate_condition

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
    assert _evaluate_condition(cond_one_of, context) == True

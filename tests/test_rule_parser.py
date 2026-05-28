import pytest

from shared.resolution.rule_parser import parse_rule_to_ast


def test_parse_neteller_brand_branch():
    text = (
        "If (PARAM_CUST_BRAND is equal to Neteller) "
        "Then ##BRAND_LOGO_NETELLER## Else ##BRAND_LOGO_SKRILL##"
    )
    ast = parse_rule_to_ast(text)
    assert ast["valid"] is True
    assert ast["kind"] == "strongmail_dynamic_content_rule"
    assert len(ast["condition"]["clauses"]) == 1
    clause = ast["condition"]["clauses"][0]
    assert clause["variable_key"] == "PARAM_CUST_BRAND"
    assert clause["operator"] == "is equal to"
    assert clause["value"] == "Neteller"
    assert ast["then"] == "##BRAND_LOGO_NETELLER##"
    assert ast["else"] == "##BRAND_LOGO_SKRILL##"


def test_parse_or_clauses():
    text = "If (A is equal to 1 Or B is equal to 2) Then X"
    ast = parse_rule_to_ast(text)
    assert ast["valid"] is True
    assert len(ast["condition"]["clauses"]) == 2
    assert ast["condition"]["combiner"] == "or"
    assert ast["else"] is None


def test_parse_is_not_null():
    text = "If (FOO is not null) Then BAR"
    ast = parse_rule_to_ast(text)
    assert ast["valid"] is True
    assert ast["condition"]["clauses"][0]["operator"] == "is not null"
    assert ast["condition"]["clauses"][0]["value"] == ""


def test_parse_invalid_empty():
    assert parse_rule_to_ast("")["valid"] is False
    assert parse_rule_to_ast("   ")["valid"] is False
    assert parse_rule_to_ast("not a rule")["valid"] is False


def test_parse_brand_color_style_rule():
    text = (
        'If (PARAM_CUST_BRAND is equal to Neteller) Then "###255F11##" '
        'Else BRAND_COLOR_BUSINESS_WALLET'
    )
    ast = parse_rule_to_ast(text)
    assert ast["valid"] is True
    assert '###255F11##' in ast["then"] or "#255F11" in ast["then"]

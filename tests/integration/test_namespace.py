import pytest
from shared.resolution.namespace import normalize_key, expand_namespace_prefix

def test_normalize_key():
    assert normalize_key("##KEY##") == "KEY"
    assert normalize_key("##/KEY##") == "KEY"
    assert normalize_key("##//KEY##") == "KEY"
    assert normalize_key("##\\KEY##") == "KEY"
    assert normalize_key("key") == "KEY"
    assert normalize_key("##key##") == "KEY"

def test_expand_namespace_prefix():
    context = {"LANG_LOCAL": "EN", "PARAM_CUST_BRAND": "SKRILL", "EMPTY": ""}
    
    assert expand_namespace_prefix("LANG_LOCAL.PARAGRAPH_1", context) == "EN.PARAGRAPH_1"
    assert expand_namespace_prefix("PARAM_CUST_BRAND.LOGO", context) == "SKRILL.LOGO"
    
    # Not in context
    assert expand_namespace_prefix("UNKNOWN.KEY", context) == "UNKNOWN.KEY"
    
    # Empty value in context
    assert expand_namespace_prefix("EMPTY.KEY", context) == "EMPTY.KEY"
    
    # No dot
    assert expand_namespace_prefix("LANG_LOCAL", context) == "LANG_LOCAL"

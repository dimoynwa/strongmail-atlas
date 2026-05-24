import types

import pytest

from shared.resolution.preprocessors import (
    ENOPENTAG_KEY,
    FIXED_MAILINGID_KEY,
    FIXED_MAILINGID_VALUE,
    SM_RULE_BRAND_COLOR_KEY,
    preprocess_key,
)
from shared.resolution.resolver import resolve_body


def test_namespace_and_brandname_preprocessing():
    context = {"PARAM_CUST_BRAND": "SKRILL"}
    assert preprocess_key("PARAM_CUST_BRAND.BRANDNAME", context) == "__BRANDNAME_DISP_SKRILL__"
    assert context["__BRANDNAME_DISP_SKRILL__"] == "Skrill"


def test_fixed_mailing_id_preprocessing():
    context: dict[str, str] = {}
    assert preprocess_key("MAILINGID", context) == FIXED_MAILINGID_KEY
    assert context[FIXED_MAILINGID_KEY] == FIXED_MAILINGID_VALUE


def test_fsp_capitalize_preprocessing():
    context = {"FIRST_NAME": "john"}
    assert preprocess_key("[F][S][P][FIRST_NAME]", context) == "__FSP_FIRST_NAME__"
    assert context["__FSP_FIRST_NAME__"] == "John"


def test_sm_rule_brand_color_preprocessing():
    context = {"PARAM_CUST_BRAND": "NETELLER"}
    assert preprocess_key("SM_RULE_BRAND_COLOR", context) == SM_RULE_BRAND_COLOR_KEY
    assert context[SM_RULE_BRAND_COLOR_KEY] == "#255F11"


def test_sm_rule_brand_logo_delegates_to_skrill():
    context = {"PARAM_CUST_BRAND": "SKRILL"}
    assert preprocess_key("SM_RULE_BRAND_LOGO", context) == "GENERAL_HEADER_LOGO_SKRILL"


def test_enopentag_preprocessing():
    context: dict[str, str] = {}
    assert preprocess_key("ENOPENTAG", context) == ENOPENTAG_KEY
    assert context[ENOPENTAG_KEY] == ""


@pytest.mark.asyncio
async def test_resolver_uses_preprocessors(db_pool, redis_client):
    graph = types.MappingProxyType({})
    body = "Campaign ##MAILINGID## brand ##\\PARAM_CUST_BRAND.BRANDNAME##"
    context = {"PARAM_CUST_BRAND": "SKRILL"}

    result = await resolve_body(
        db_pool,
        redis_client,
        graph,
        body,
        context,
        "preprocess-session",
        "T1",
    )

    assert result.resolved_body == "Campaign 1914 brand Skrill"
    assert result.unresolvable == []

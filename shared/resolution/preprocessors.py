"""Placeholder key preprocessors applied before graph / Redis / SM_RULE lookup."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

ARGDELIMITER_SPACE_KEY = "__ARGDELIMITER_SPACE__"
IGNCLICKTAG_SPACE_KEY = "__IGNCLICKTAG_SPACE__"
FIXED_MAILINGID_KEY = "__FIXED_MAILINGID__"
FIXED_MAILINGID_VALUE = "1914"
SM_RULE_BRAND_COLOR_KEY = "__SM_RULE_BRAND_COLOR__"
SM_RULE_BRAND_COLOR_DARK_THEME_HIPERLINKS_KEY = "__SM_RULE_BRAND_COLOR_DARK_THEME_HIPERLINKS__"
SM_RULE_BRAND_COLOR_DARK_THEME_KEY = "__SM_RULE_BRAND_COLOR_DARK_THEME__"
SM_RULE_BRAND_FONT_KEY = "__SM_RULE_BRAND_FONT__"
SM_RULE_BRAND_BURGER_MENU_KEY = "__SM_RULE_BRAND_BURGER_MENU__"
SM_RULE_BRAND_BURGER_MENU_COLOR_KEY = "__SM_RULE_BRAND_BURGER_MENU_COLOR__"
SM_RULE_BRAND_BURGER_WRAPPER_COLOR_KEY = "__SM_RULE_BRAND_BURGER_WRAPPER_COLOR__"
GENERAL_GREY_FOOTER_NAV_KEY = "__GENERAL_GREY_FOOTER_NAV__"
ENOPENTAG_KEY = "__ENOPENTAG__"
VIEW_TRANSACTION_BUTTON_KEY = "__VIEW_TRANSACTION_BUTTON__"
TRANSACTION_DETAILS_TABLE_KEY = "__TRANSACTION_DETAILS_TABLE__"
ENVIEWINBROWSERTAG_KEY = "__ENVIEWINBROWSERTAG__"
MS_ORG_ID_KEY = "__MS_ORG_ID__"
PARAM_CUST_ACC_URL_KEY = "__PARAM_CUST_ACC_URL__"
SM_RULE_SKIP_KEY = "__SM_RULE_SKIP__"

SKRILL_ACCOUNT_URL = "https://account.skrill.com/wallet"
NETELLER_ACCOUNT_URL = "https://member.neteller.com/wallet/account/login"

NETELLER_COLOR = "#255F11"
DEFAULT_BRAND_COLOR = "#910590"
NETELLER_COLOR_DARK_THEME_HIPERLINKS = "#5B981D"
DEFAULT_COLOR_DARK_THEME_HIPERLINKS = "#D656D6"
NETELLER_COLOR_DARK_THEME = "#5B981D"
DEFAULT_COLOR_DARK_THEME = "#B53FB5"
NETELLER_FONT = "'Open Sans', sans-serif"
DEFAULT_BRAND_FONT = "'Source Sans Pro', sans-serif"
NETELLER_BURGER_MENU_COLOR = "#8fb850"
DEFAULT_BURGER_MENU_COLOR = "#592357"
NETELLER_BURGER_MENU_COLOR_VALUE = "#73a747"
DEFAULT_BURGER_MENU_COLOR_VALUE = "#67235e"

GENERAL_HEADER_LOGO_NETELLER = "GENERAL_HEADER_LOGO_NETELLER"
GENERAL_HEADER_LOGO_SKRILL = "GENERAL_HEADER_LOGO_SKRILL"
GENERAL_HEADER_LOGO_2_NETELLER = "GENERAL_HEADER_LOGO_2_NETELLER"
GENERAL_HEADER_LOGO_2_SKRILL = "GENERAL_HEADER_LOGO_2_SKRILL"
GENERAL_SIGN_OFF_LOGO_NETELLER = "GENERAL_SIGN_OFF_LOGO_NETELLER"
GENERAL_SIGN_OFF_LOGO_SKRILL = "GENERAL_SIGN_OFF_LOGO_SKRILL"
GENERAL_FOOTER_NETELLER = "GENERAL_FOOTER_NETELLER"
GENERAL_FOOTER_LTD = "GENERAL_FOOTER_LTD"
GENERAL_FOOTER_NETELLER_PREPAID_PML_ARG = "GENERAL_FOOTER_NETELLER_PREPAID_PML_ARG"
GENERAL_FOOTER_PREPAID_PML_ARG = "GENERAL_FOOTER_PREPAID_PML_ARG"
GENERAL_FOOTER_EEA_UPDATED = "GENERAL_FOOTER_EEA_UPDATED"
GENERAL_HERO_1_NETELLER = "GENERAL_HERO_1_NETELLER"
GENERAL_HERO_1_SKRILL = "GENERAL_HERO_1_SKRILL"

_IGNCLICKTAG_KEY_PATTERN = re.compile(r"^IGNCLICKTAG\d+$", re.IGNORECASE)
_FSP_PATTERN = re.compile(r"^\[F\]\[S\]\[P\]\[(?:\\)*([A-Za-z0-9_.]+)\]$")
_NAMESPACE_KEYS = frozenset({"LANG_LOCAL", "PARAM_CUST_BRAND"})


def parameters_get_ci(parameters: dict[str, str], key: str) -> str | None:
    target = key.upper()
    for param_key, value in parameters.items():
        if param_key.upper() == target:
            return value
    return None


def is_synthetic_context_key(key: str) -> bool:
    return key.startswith("__")


class PlaceholderPreprocessor(ABC):
    @abstractmethod
    def process(self, key: str, context: dict[str, str]) -> str:
        pass


class PlaceholderPreprocessorPipeline:
    def __init__(self, preprocessors: list[PlaceholderPreprocessor]) -> None:
        self.preprocessors = preprocessors

    def process(self, key: str, context: dict[str, str]) -> str:
        for preprocessor in self.preprocessors:
            key = preprocessor.process(key, context)
        return key


def _skip_sm_rules(context: dict[str, str]) -> bool:
    value = parameters_get_ci(context, "SKIP_SM_RULES_CHECKS") or ""
    return str(value).lower() in ("true", "1", "yes")


def _brand(context: dict[str, str]) -> str:
    return (parameters_get_ci(context, "PARAM_CUST_BRAND") or "").upper()


def _inject(context: dict[str, str], synth_key: str, value: str) -> str:
    context[synth_key] = value
    return synth_key


def _skip_or_delegate(
    key: str,
    context: dict[str, str],
    rule_name: str,
    neteller_target: str,
    default_target: str,
) -> str:
    if key != rule_name:
        return key
    if _skip_sm_rules(context):
        return _inject(context, SM_RULE_SKIP_KEY, "")
    return neteller_target if _brand(context) == "NETELLER" else default_target


class FspCapitalizePreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        match = _FSP_PATTERN.match(key)
        if not match:
            return key
        param_name = match.group(1).upper()
        raw = parameters_get_ci(context, param_name) or ""
        capitalized = raw.capitalize() if raw else ""
        synth_key = f"__FSP_{param_name}__"
        return _inject(context, synth_key, capitalized)


class ArgDelimiterSpacePreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key == "ARGDELIMITER":
            return _inject(context, ARGDELIMITER_SPACE_KEY, " ")
        return key


class IgnClickTagSpacePreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if _IGNCLICKTAG_KEY_PATTERN.match(key):
            return _inject(context, IGNCLICKTAG_SPACE_KEY, " ")
        return key


class FixedMailingIdPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key == "MAILINGID":
            return _inject(context, FIXED_MAILINGID_KEY, FIXED_MAILINGID_VALUE)
        return key


class EnopentagPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key == "ENOPENTAG":
            return _inject(context, ENOPENTAG_KEY, "")
        return key


class GeneralGreyFooterNavPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key == "GENERAL_GREY_FOOTER_NAV":
            return _inject(context, GENERAL_GREY_FOOTER_NAV_KEY, "")
        return key


class ViewTransactionButtonPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key == "VIEW_TRANSACTION_BUTTON":
            return _inject(context, VIEW_TRANSACTION_BUTTON_KEY, "")
        return key


class TransactionDetailsTablePreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key == "TRANSACTION_DETAILS_TABLE":
            return _inject(context, TRANSACTION_DETAILS_TABLE_KEY, "")
        return key


class EnviewInBrowserTagPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key == "ENVIEWINBROWSERTAG":
            return _inject(context, ENVIEWINBROWSERTAG_KEY, "")
        return key


class MsOrgIdPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key == "_MS_ORG_ID":
            return _inject(context, MS_ORG_ID_KEY, "")
        return key


class ParamCustAccUrlPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key != "PARAM_CUST_ACC_URL":
            return key
        url = SKRILL_ACCOUNT_URL if _brand(context) == "SKRILL" else NETELLER_ACCOUNT_URL
        return _inject(context, PARAM_CUST_ACC_URL_KEY, url)


class NamespacePreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        while "." in key:
            prefix, _, suffix = key.partition(".")
            namespace_value = parameters_get_ci(context, prefix)
            if namespace_value is None or not isinstance(namespace_value, str) or not namespace_value:
                break
            if prefix.upper() in _NAMESPACE_KEYS:
                namespace_value = namespace_value.upper()
            key = f"{namespace_value}.{suffix}"
        return key


class BrandNameDisplayPreprocessor(PlaceholderPreprocessor):
    _suffix = ".BRANDNAME"

    def process(self, key: str, context: dict[str, str]) -> str:
        if not key.endswith(self._suffix):
            return key
        base = key[: -len(self._suffix)]
        if not base:
            return key
        token = base.rsplit(".", 1)[-1]
        if not token:
            return key
        display = token.lower().capitalize()
        synth_key = f"__BRANDNAME_DISP_{token.upper()}__"
        return _inject(context, synth_key, display)


class SmRuleBrandColorPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key != "SM_RULE_BRAND_COLOR":
            return key
        color = NETELLER_COLOR if _brand(context) == "NETELLER" else DEFAULT_BRAND_COLOR
        return _inject(context, SM_RULE_BRAND_COLOR_KEY, color)


class SmRuleBrandColorDarkThemePreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key != "SM_RULE_BRAND_COLOR_DARK_THEME":
            return key
        color = NETELLER_COLOR_DARK_THEME if _brand(context) == "NETELLER" else DEFAULT_COLOR_DARK_THEME
        return _inject(context, SM_RULE_BRAND_COLOR_DARK_THEME_KEY, color)


class SmRuleBrandColorDarkThemeHyperlinksPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key != "SM_RULE_BRAND_COLOR_DARK_THEME_HIPERLINKS":
            return key
        color = (
            NETELLER_COLOR_DARK_THEME_HIPERLINKS
            if _brand(context) == "NETELLER"
            else DEFAULT_COLOR_DARK_THEME_HIPERLINKS
        )
        return _inject(context, SM_RULE_BRAND_COLOR_DARK_THEME_HIPERLINKS_KEY, color)


class SmRuleBrandFontPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key != "SM_RULE_BRAND_FONT":
            return key
        if _skip_sm_rules(context):
            return _inject(context, SM_RULE_SKIP_KEY, "")
        font = NETELLER_FONT if _brand(context) == "NETELLER" else DEFAULT_BRAND_FONT
        return _inject(context, SM_RULE_BRAND_FONT_KEY, font)


class SmRuleBrandBurgerMenuPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key != "SM_RULE_BRAND_BURGER_MENU":
            return key
        color = NETELLER_BURGER_MENU_COLOR if _brand(context) == "NETELLER" else DEFAULT_BURGER_MENU_COLOR
        return _inject(context, SM_RULE_BRAND_BURGER_MENU_KEY, color)


class SmRuleBrandBurgerMenuColorPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key != "SM_RULE_BRAND_BURGER_MENU_COLOR":
            return key
        color = (
            NETELLER_BURGER_MENU_COLOR_VALUE
            if _brand(context) == "NETELLER"
            else DEFAULT_BURGER_MENU_COLOR_VALUE
        )
        return _inject(context, SM_RULE_BRAND_BURGER_MENU_COLOR_KEY, color)


class SmRuleBrandBurgerWrapperColorPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key != "SM_RULE_BRAND_BURGER_WRAPPER_COLOR":
            return key
        color = (
            NETELLER_BURGER_MENU_COLOR_VALUE
            if _brand(context) == "NETELLER"
            else DEFAULT_BURGER_MENU_COLOR_VALUE
        )
        return _inject(context, SM_RULE_BRAND_BURGER_WRAPPER_COLOR_KEY, color)


class SmRuleBrandLogoPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        return _skip_or_delegate(
            key,
            context,
            "SM_RULE_BRAND_LOGO",
            GENERAL_HEADER_LOGO_NETELLER,
            GENERAL_HEADER_LOGO_SKRILL,
        )


class SmRuleGeneralBrandLogo2Preprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        return _skip_or_delegate(
            key,
            context,
            "SM_RULE_GENERAL_BRAND_LOGO_2",
            GENERAL_HEADER_LOGO_2_NETELLER,
            GENERAL_HEADER_LOGO_2_SKRILL,
        )


class SmRuleBrandSignOffLogoPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        return _skip_or_delegate(
            key,
            context,
            "SM_RULE_BRAND_SIGN_OFF_LOGO",
            GENERAL_SIGN_OFF_LOGO_NETELLER,
            GENERAL_SIGN_OFF_LOGO_SKRILL,
        )


class SmRuleBrandFooterPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        return _skip_or_delegate(
            key,
            context,
            "SM_RULE_BRAND_FOOTER",
            GENERAL_FOOTER_NETELLER,
            GENERAL_FOOTER_LTD,
        )


class SmRuleBrandFooterPrepaidPmlPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        return _skip_or_delegate(
            key,
            context,
            "SM_RULE_BRAND_FOOTER_PREPAID_PML",
            GENERAL_FOOTER_NETELLER_PREPAID_PML_ARG,
            GENERAL_FOOTER_PREPAID_PML_ARG,
        )


class SmRuleFooterTermsPreprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        if key != "SM_RULE_FOOTER_TERMS":
            return key
        if _skip_sm_rules(context):
            return _inject(context, SM_RULE_SKIP_KEY, "")
        return GENERAL_FOOTER_EEA_UPDATED


class SmRuleBrandHero1Preprocessor(PlaceholderPreprocessor):
    def process(self, key: str, context: dict[str, str]) -> str:
        return _skip_or_delegate(
            key,
            context,
            "SM_RULE_BRAND_HERO_1",
            GENERAL_HERO_1_NETELLER,
            GENERAL_HERO_1_SKRILL,
        )


def default_preprocessor_pipeline() -> PlaceholderPreprocessorPipeline:
    return PlaceholderPreprocessorPipeline(
        [
            FspCapitalizePreprocessor(),
            ArgDelimiterSpacePreprocessor(),
            IgnClickTagSpacePreprocessor(),
            FixedMailingIdPreprocessor(),
            EnopentagPreprocessor(),
            GeneralGreyFooterNavPreprocessor(),
            ViewTransactionButtonPreprocessor(),
            TransactionDetailsTablePreprocessor(),
            EnviewInBrowserTagPreprocessor(),
            MsOrgIdPreprocessor(),
            ParamCustAccUrlPreprocessor(),
            NamespacePreprocessor(),
            BrandNameDisplayPreprocessor(),
            SmRuleBrandColorPreprocessor(),
            SmRuleBrandColorDarkThemePreprocessor(),
            SmRuleBrandColorDarkThemeHyperlinksPreprocessor(),
            SmRuleBrandFontPreprocessor(),
            SmRuleBrandBurgerMenuPreprocessor(),
            SmRuleBrandBurgerMenuColorPreprocessor(),
            SmRuleBrandBurgerWrapperColorPreprocessor(),
            SmRuleBrandLogoPreprocessor(),
            SmRuleGeneralBrandLogo2Preprocessor(),
            SmRuleBrandSignOffLogoPreprocessor(),
            SmRuleBrandFooterPreprocessor(),
            SmRuleBrandFooterPrepaidPmlPreprocessor(),
            SmRuleFooterTermsPreprocessor(),
            SmRuleBrandHero1Preprocessor(),
        ]
    )


_DEFAULT_PIPELINE = default_preprocessor_pipeline()


def preprocess_key(key: str, context: dict[str, str]) -> str:
    return _DEFAULT_PIPELINE.process(key, context)

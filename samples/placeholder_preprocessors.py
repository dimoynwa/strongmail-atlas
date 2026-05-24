"""Placeholder preprocessor interface and pipeline (from strongmail-email-resolution-system)."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable

from strongmail.placeholder_resolution.key_normalization import (
    canonical_placeholder_key,
    parameters_get_ci,
)
from strongmail.placeholder_resolution.models import ResolutionContext


class PlaceholderPreprocessor(ABC):
    """Transform placeholder keys before lookup (e.g., LANG_LOCAL.MESSAGE -> BG.MESSAGE)."""

    @abstractmethod
    def process(self, key: str, context: ResolutionContext) -> str:
        """Transform the key before lookup."""
        pass


class PlaceholderPreprocessorPipeline:
    """Chain of placeholder preprocessors."""

    def __init__(self, preprocessors: list[PlaceholderPreprocessor]) -> None:
        self.preprocessors = preprocessors

    def process(self, key: str, context: ResolutionContext) -> str:
        """Apply each preprocessor in sequence."""
        for p in self.preprocessors:
            key = p.process(key, context)
        return key


class IdentityPlaceholderPreprocessor(PlaceholderPreprocessor):
    """No-op placeholder preprocessor."""

    def process(self, key: str, context: ResolutionContext) -> str:
        return key


class CaseNormalizePreprocessor(PlaceholderPreprocessor):
    """
    Normalize placeholder keys to uppercase (canonical form).
    Graph and parameter lookups are case-insensitive, but this keeps preprocessor comparisons stable.
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        return key.upper()


# Lookup keys for literal space replacements (StrongMail tracking tokens stripped for readability)
ARGDELIMITER_SPACE_KEY = "__ARGDELIMITER_SPACE__"
IGNCLICKTAG_SPACE_KEY = "__IGNCLICKTAG_SPACE__"

_IGNCLICKTAG_KEY_PATTERN = re.compile(r"^IGNCLICKTAG\d+$", re.IGNORECASE)


class ArgDelimiterSpacePreprocessor(PlaceholderPreprocessor):
    """
    Replace ARGDELIMITER with a single space (e.g. StrongMail arg delimiter token).
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "ARGDELIMITER":
            context.parameters[ARGDELIMITER_SPACE_KEY] = " "
            return ARGDELIMITER_SPACE_KEY
        return key


class IgnClickTagSpacePreprocessor(PlaceholderPreprocessor):
    """
    Replace IGNCLICKTAG<number> with a single space (e.g. IGNCLICKTAG3000 -> ' ').
    Case-insensitive on the key (pipeline usually uppercases keys first).
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if _IGNCLICKTAG_KEY_PATTERN.match(key):
            context.parameters[IGNCLICKTAG_SPACE_KEY] = " "
            return IGNCLICKTAG_SPACE_KEY
        return key


class BrandNameDisplayPreprocessor(PlaceholderPreprocessor):
    """
    Replace *.<BRANDNAME> placeholders with a display form of the brand token before ``.BRANDNAME``.

    Examples: SKRILL.BRANDNAME -> Skrill, NETELLER.BRANDNAME -> Neteller.

    The segment before ``.BRANDNAME`` is lowercased then capitalized (first letter upper, rest lower).
    If multiple dot segments exist (e.g. PREFIX.SKRILL.BRANDNAME), only the segment immediately
    before ``.BRANDNAME`` is used for the display text.
    """

    _suffix = ".BRANDNAME"

    def process(self, key: str, context: ResolutionContext) -> str:
        if not key.endswith(self._suffix):
            return key
        base = key[: -len(self._suffix)]
        if not base:
            return key
        token = base.rsplit(".", 1)[-1]
        if not token:
            return key
        display = token.lower().capitalize()
        synth_key = f"__BRANDNAME_DISP_{canonical_placeholder_key(token)}__"
        context.parameters[synth_key] = display
        return synth_key


# Lookup key for fixed MAILINGID value (injected into context at resolution time)
FIXED_MAILINGID_KEY = "__FIXED_MAILINGID__"
FIXED_MAILINGID_VALUE = "1914"


# Lookup key for SM_RULE_BRAND_COLOR (value computed from PARAM_CUST_BRAND)
SM_RULE_BRAND_COLOR_KEY = "__SM_RULE_BRAND_COLOR__"
NETELLER_COLOR = "#255F11"
DEFAULT_BRAND_COLOR = "#910590"


# Lookup key for SM_RULE_BRAND_COLOR_DARK_THEME_HIPERLINKS (value computed from PARAM_CUST_BRAND)
SM_RULE_BRAND_COLOR_DARK_THEME_HIPERLINKS_KEY = "__SM_RULE_BRAND_COLOR_DARK_THEME_HIPERLINKS__"
NETELLER_COLOR_DARK_THEME_HIPERLINKS = "#5B981D"
DEFAULT_COLOR_DARK_THEME_HIPERLINKS = "#D656D6"

# Lookup key for SM_RULE_BRAND_COLOR_DARK_THEME (value computed from PARAM_CUST_BRAND)
SM_RULE_BRAND_COLOR_DARK_THEME_KEY = "__SM_RULE_BRAND_COLOR_DARK_THEME__"
NETELLER_COLOR_DARK_THEME = "#5B981D"
DEFAULT_COLOR_DARK_THEME = "#B53FB5"


# Lookup key for SM_RULE_BRAND_FONT (value computed from PARAM_CUST_BRAND)
SM_RULE_BRAND_FONT_KEY = "__SM_RULE_BRAND_FONT__"
NETELLER_FONT = "'Open Sans', sans-serif"
DEFAULT_BRAND_FONT = "'Source Sans Pro', sans-serif"

# Lookup key for SM_RULE_BRAND_BURGER_MENU (value computed from PARAM_CUST_BRAND)
SM_RULE_BRAND_BURGER_MENU_KEY = "__SM_RULE_BRAND_BURGER_MENU__"
NETELLER_BURGER_MENU_COLOR = "#8fb850"
DEFAULT_BURGER_MENU_COLOR = "#592357"

# Lookup key for SM_RULE_BRAND_BURGER_MENU_COLOR (value computed from PARAM_CUST_BRAND)
SM_RULE_BRAND_BURGER_MENU_COLOR_KEY = "__SM_RULE_BRAND_BURGER_MENU_COLOR__"
# Lookup key for SM_RULE_BRAND_BURGER_WRAPPER_COLOR (value computed from PARAM_CUST_BRAND)
SM_RULE_BRAND_BURGER_WRAPPER_COLOR_KEY = "__SM_RULE_BRAND_BURGER_WRAPPER_COLOR__"
NETELLER_BURGER_MENU_COLOR_VALUE = "#73a747"
DEFAULT_BURGER_MENU_COLOR_VALUE = "#67235e"

# Placeholder keys for SM_RULE_BRAND_LOGO (delegates to brand-specific logo placeholder)
GENERAL_HEADER_LOGO_NETELLER = "GENERAL_HEADER_LOGO_NETELLER"
GENERAL_HEADER_LOGO_SKRILL = "GENERAL_HEADER_LOGO_SKRILL"

# Placeholder keys for SM_RULE_GENERAL_BRAND_LOGO_2 (delegates to brand-specific logo 2 placeholder)
GENERAL_HEADER_LOGO_2_NETELLER = "GENERAL_HEADER_LOGO_2_NETELLER"
GENERAL_HEADER_LOGO_2_SKRILL = "GENERAL_HEADER_LOGO_2_SKRILL"

# Placeholder keys for SM_RULE_BRAND_SIGN_OFF_LOGO (delegates to brand-specific sign-off logo)
GENERAL_SIGN_OFF_LOGO_NETELLER = "GENERAL_SIGN_OFF_LOGO_NETELLER"
GENERAL_SIGN_OFF_LOGO_SKRILL = "GENERAL_SIGN_OFF_LOGO_SKRILL"

# Placeholder keys for SM_RULE_BRAND_FOOTER (delegates to brand-specific footer placeholder)
GENERAL_FOOTER_NETELLER = "GENERAL_FOOTER_NETELLER"
GENERAL_FOOTER_LTD = "GENERAL_FOOTER_LTD"

# Placeholder keys for SM_RULE_BRAND_FOOTER_PREPAID_PML (delegates to brand-specific footer placeholder)
GENERAL_FOOTER_NETELLER_PREPAID_PML_ARG = "GENERAL_FOOTER_NETELLER_PREPAID_PML_ARG"
GENERAL_FOOTER_PREPAID_PML_ARG = "GENERAL_FOOTER_PREPAID_PML_ARG"

# Placeholder key for SM_RULE_FOOTER_TERMS (always delegates to GENERAL_FOOTER_EEA_UPDATED)
GENERAL_FOOTER_EEA_UPDATED = "GENERAL_FOOTER_EEA_UPDATED"

# Placeholder keys for SM_RULE_BRAND_HERO_1 (delegates to brand-specific hero placeholder)
GENERAL_HERO_1_NETELLER = "GENERAL_HERO_1_NETELLER"
GENERAL_HERO_1_SKRILL = "GENERAL_HERO_1_SKRILL"

# Lookup key for GENERAL_GREY_FOOTER_NAV (always resolves to empty string)
GENERAL_GREY_FOOTER_NAV_KEY = "__GENERAL_GREY_FOOTER_NAV__"

# Lookup key for ENOPENTAG (always resolves to empty string)
ENOPENTAG_KEY = "__ENOPENTAG__"

# Lookup key when SKIP_SM_RULES_CHECKS is true (all SmRule preprocessors return empty)
SM_RULE_SKIP_KEY = "__SM_RULE_SKIP__"


def _skip_sm_rules(context: ResolutionContext) -> bool:
    """Return True if SKIP_SM_RULES_CHECKS is set to a truthy value in context."""
    val = parameters_get_ci(context.parameters, "SKIP_SM_RULES_CHECKS") or ""
    return str(val).lower() in ("true", "1", "yes")


# Regex for [F][S][P][PARAM] format (capitalize first letter of param value).
# StrongMail often emits a backslash before the param: [F][S][P][\FIRST_NAME] (same as ##\\KEY##).
_FSP_PATTERN = re.compile(r"^\[F\]\[S\]\[P\]\[(?:\\)*([A-Za-z0-9_.]+)\]$")


class FspCapitalizePreprocessor(PlaceholderPreprocessor):
    """
    Resolve ##[F][S][P][PARAM]## by looking up PARAM in context and capitalizing first letter.
    E.g. [F][S][P][FIRST_NAME] or [F][S][P][\\FIRST_NAME] with FIRST_NAME="john" → "John".
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        m = _FSP_PATTERN.match(key)
        if m:
            param_name = m.group(1)
            raw = parameters_get_ci(context.parameters, param_name) or ""
            capitalized = raw.capitalize() if raw else ""
            synth_key = f"__FSP_{param_name}__"
            context.parameters[synth_key] = capitalized
            return synth_key
        return key


class EnopentagPreprocessor(PlaceholderPreprocessor):
    """
    Resolve ENOPENTAG to empty string.
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "ENOPENTAG":
            context.parameters[ENOPENTAG_KEY] = ""
            return ENOPENTAG_KEY
        return key


class GeneralGreyFooterNavPreprocessor(PlaceholderPreprocessor):
    """
    Resolve GENERAL_GREY_FOOTER_NAV to empty string.
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "GENERAL_GREY_FOOTER_NAV":
            context.parameters[GENERAL_GREY_FOOTER_NAV_KEY] = ""
            return GENERAL_GREY_FOOTER_NAV_KEY
        return key


class SmRuleBrandFooterPreprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_BRAND_FOOTER by delegating to brand-specific placeholder.
    NETELLER (uppercase) → GENERAL_FOOTER_NETELLER, otherwise → GENERAL_FOOTER_LTD.
    These are placeholders that the resolver will look up and resolve recursively.
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "SM_RULE_BRAND_FOOTER":
            if _skip_sm_rules(context):
                context.parameters[SM_RULE_SKIP_KEY] = ""
                return SM_RULE_SKIP_KEY
            brand = (parameters_get_ci(context.parameters, "PARAM_CUST_BRAND") or "").upper()
            return GENERAL_FOOTER_NETELLER if brand == "NETELLER" else GENERAL_FOOTER_LTD
        return key


class SmRuleBrandFooterPrepaidPmlPreprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_BRAND_FOOTER_PREPAID_PML by delegating to brand-specific placeholder.
    NETELLER (uppercase) → GENERAL_FOOTER_NETELLER_PREPAID_PML_ARG, otherwise → GENERAL_FOOTER_PREPAID_PML_ARG.
    These are placeholders that the resolver will look up and resolve recursively.
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "SM_RULE_BRAND_FOOTER_PREPAID_PML":
            if _skip_sm_rules(context):
                context.parameters[SM_RULE_SKIP_KEY] = ""
                return SM_RULE_SKIP_KEY
            brand = (parameters_get_ci(context.parameters, "PARAM_CUST_BRAND") or "").upper()
            return (
                GENERAL_FOOTER_NETELLER_PREPAID_PML_ARG
                if brand == "NETELLER"
                else GENERAL_FOOTER_PREPAID_PML_ARG
            )
        return key


class SmRuleFooterTermsPreprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_FOOTER_TERMS by delegating to GENERAL_FOOTER_EEA_UPDATED.
    The resolver will look up and resolve GENERAL_FOOTER_EEA_UPDATED recursively.
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "SM_RULE_FOOTER_TERMS":
            if _skip_sm_rules(context):
                context.parameters[SM_RULE_SKIP_KEY] = ""
                return SM_RULE_SKIP_KEY
            return GENERAL_FOOTER_EEA_UPDATED
        return key


class SmRuleBrandSignOffLogoPreprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_BRAND_SIGN_OFF_LOGO by delegating to brand-specific placeholder.
    NETELLER (uppercase) → GENERAL_SIGN_OFF_LOGO_NETELLER, otherwise → GENERAL_SIGN_OFF_LOGO_SKRILL.
    These are placeholders that the resolver will look up and resolve recursively.
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "SM_RULE_BRAND_SIGN_OFF_LOGO":
            if _skip_sm_rules(context):
                context.parameters[SM_RULE_SKIP_KEY] = ""
                return SM_RULE_SKIP_KEY
            brand = (parameters_get_ci(context.parameters, "PARAM_CUST_BRAND") or "").upper()
            return (
                GENERAL_SIGN_OFF_LOGO_NETELLER
                if brand == "NETELLER"
                else GENERAL_SIGN_OFF_LOGO_SKRILL
            )
        return key


class SmRuleGeneralBrandLogo2Preprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_GENERAL_BRAND_LOGO_2 by delegating to brand-specific placeholder.
    NETELLER (uppercase) → GENERAL_HEADER_LOGO_2_NETELLER, otherwise → GENERAL_HEADER_LOGO_2_SKRILL.
    These are placeholders that the resolver will look up and resolve recursively.
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "SM_RULE_GENERAL_BRAND_LOGO_2":
            if _skip_sm_rules(context):
                context.parameters[SM_RULE_SKIP_KEY] = ""
                return SM_RULE_SKIP_KEY
            brand = (parameters_get_ci(context.parameters, "PARAM_CUST_BRAND") or "").upper()
            return (
                GENERAL_HEADER_LOGO_2_NETELLER
                if brand == "NETELLER"
                else GENERAL_HEADER_LOGO_2_SKRILL
            )
        return key


class SmRuleBrandLogoPreprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_BRAND_LOGO by delegating to brand-specific placeholder.
    NETELLER (uppercase) → GENERAL_HEADER_LOGO_NETELLER, otherwise → GENERAL_HEADER_LOGO_SKRILL.
    These are placeholders that the resolver will look up and resolve recursively.
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "SM_RULE_BRAND_LOGO":
            if _skip_sm_rules(context):
                context.parameters[SM_RULE_SKIP_KEY] = ""
                return SM_RULE_SKIP_KEY
            brand = (parameters_get_ci(context.parameters, "PARAM_CUST_BRAND") or "").upper()
            return (
                GENERAL_HEADER_LOGO_NETELLER
                if brand == "NETELLER"
                else GENERAL_HEADER_LOGO_SKRILL
            )
        return key


def _sm_rule_dyn_key(rule_name: str) -> str:
    """Synthetic key for injecting dynamic rule result into context."""
    return f"__SM_RULE_DYN_{rule_name}__"


class SmRuleDynamicContentPreprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_* placeholders using rule text from ``rule_text_getter`` (e.g. PostgreSQL).

    Same evaluation semantics as strongmail-email-resolution-system, but rules are loaded via
    callback instead of ``data/dynamic_content`` files.
    """

    def __init__(self, rule_text_getter: Callable[[str], str | None]) -> None:
        self._rule_text_getter = rule_text_getter

    def process(self, key: str, context: ResolutionContext) -> str:
        if not key.startswith("SM_RULE_"):
            return key
        if _skip_sm_rules(context):
            context.parameters[SM_RULE_SKIP_KEY] = ""
            return SM_RULE_SKIP_KEY
        rule_name = key[8:]  # strip "SM_RULE_"
        if not rule_name:
            return key
        from .rule_engine import evaluate_rule_from_text

        content = self._rule_text_getter(rule_name)
        if not content:
            return key
        result = evaluate_rule_from_text(content, context.parameters)
        if not result:
            return key
        if "##" in result and not _is_simple_placeholder_key(result):
            synth_key = _sm_rule_dyn_key(rule_name)
            context.parameters[synth_key] = result
            return synth_key
        return result


def _is_simple_placeholder_key(s: str) -> bool:
    """True if s is a simple lookup key (no embedded ## placeholders)."""
    return bool(re.match(r"^[A-Za-z0-9_.]+$", s)) or s.startswith("SM_RULE_")


class SmRuleBrandHero1Preprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_BRAND_HERO_1 by delegating to brand-specific placeholder.
    NETELLER (uppercase) → GENERAL_HERO_1_NETELLER, otherwise → GENERAL_HERO_1_SKRILL.
    These are placeholders that the resolver will look up and resolve recursively.
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "SM_RULE_BRAND_HERO_1":
            if _skip_sm_rules(context):
                context.parameters[SM_RULE_SKIP_KEY] = ""
                return SM_RULE_SKIP_KEY
            brand = (parameters_get_ci(context.parameters, "PARAM_CUST_BRAND") or "").upper()
            return (
                GENERAL_HERO_1_NETELLER
                if brand == "NETELLER"
                else GENERAL_HERO_1_SKRILL
            )
        return key


class SmRuleBrandColorDarkThemePreprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_BRAND_COLOR_DARK_THEME from PARAM_CUST_BRAND in context.
    NETELLER (uppercase) → "#5B981D", otherwise → "#B53FB5".
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "SM_RULE_BRAND_COLOR_DARK_THEME":
            brand = (parameters_get_ci(context.parameters, "PARAM_CUST_BRAND") or "").upper()
            color = (
                NETELLER_COLOR_DARK_THEME
                if brand == "NETELLER"
                else DEFAULT_COLOR_DARK_THEME
            )
            context.parameters[SM_RULE_BRAND_COLOR_DARK_THEME_KEY] = color
            return SM_RULE_BRAND_COLOR_DARK_THEME_KEY
        return key


class SmRuleBrandColorDarkThemeHyperlinksPreprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_BRAND_COLOR_DARK_THEME_HIPERLINKS from PARAM_CUST_BRAND in context.
    NETELLER (uppercase) → "#5B981D", otherwise → "#D656D6".
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "SM_RULE_BRAND_COLOR_DARK_THEME_HIPERLINKS":
            brand = (parameters_get_ci(context.parameters, "PARAM_CUST_BRAND") or "").upper()
            color = (
                NETELLER_COLOR_DARK_THEME_HIPERLINKS
                if brand == "NETELLER"
                else DEFAULT_COLOR_DARK_THEME_HIPERLINKS
            )
            context.parameters[SM_RULE_BRAND_COLOR_DARK_THEME_HIPERLINKS_KEY] = color
            return SM_RULE_BRAND_COLOR_DARK_THEME_HIPERLINKS_KEY
        return key


class SmRuleBrandFontPreprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_BRAND_FONT from PARAM_CUST_BRAND in context.
    NETELLER (uppercase) → "'Open Sans', sans-serif", otherwise → "'Source Sans Pro', sans-serif".
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "SM_RULE_BRAND_FONT":
            if _skip_sm_rules(context):
                context.parameters[SM_RULE_SKIP_KEY] = ""
                return SM_RULE_SKIP_KEY
            brand = (parameters_get_ci(context.parameters, "PARAM_CUST_BRAND") or "").upper()
            font = NETELLER_FONT if brand == "NETELLER" else DEFAULT_BRAND_FONT
            context.parameters[SM_RULE_BRAND_FONT_KEY] = font
            return SM_RULE_BRAND_FONT_KEY
        return key


class SmRuleBrandColorPreprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_BRAND_COLOR from PARAM_CUST_BRAND in context.
    NETELLER (uppercase) → "#255F11", otherwise → "#910590".
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "SM_RULE_BRAND_COLOR":
            brand = (
                parameters_get_ci(context.parameters, "PARAM_CUST_BRAND") or ""
            ).upper()
            color = NETELLER_COLOR if brand == "NETELLER" else DEFAULT_BRAND_COLOR
            context.parameters[SM_RULE_BRAND_COLOR_KEY] = color
            return SM_RULE_BRAND_COLOR_KEY
        return key


class SmRuleBrandBurgerMenuPreprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_BRAND_BURGER_MENU from PARAM_CUST_BRAND in context.
    NETELLER (uppercase) → "#8fb850", otherwise → "#592357".
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "SM_RULE_BRAND_BURGER_MENU":
            brand = (parameters_get_ci(context.parameters, "PARAM_CUST_BRAND") or "").upper()
            color = (
                NETELLER_BURGER_MENU_COLOR
                if brand == "NETELLER"
                else DEFAULT_BURGER_MENU_COLOR
            )
            context.parameters[SM_RULE_BRAND_BURGER_MENU_KEY] = color
            return SM_RULE_BRAND_BURGER_MENU_KEY
        return key


class SmRuleBrandBurgerMenuColorPreprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_BRAND_BURGER_MENU_COLOR from PARAM_CUST_BRAND in context.
    NETELLER (uppercase) → "#73a747", otherwise → "#67235e".
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "SM_RULE_BRAND_BURGER_MENU_COLOR":
            brand = (parameters_get_ci(context.parameters, "PARAM_CUST_BRAND") or "").upper()
            color = (
                NETELLER_BURGER_MENU_COLOR_VALUE
                if brand == "NETELLER"
                else DEFAULT_BURGER_MENU_COLOR_VALUE
            )
            context.parameters[SM_RULE_BRAND_BURGER_MENU_COLOR_KEY] = color
            return SM_RULE_BRAND_BURGER_MENU_COLOR_KEY
        return key


class SmRuleBrandBurgerWrapperColorPreprocessor(PlaceholderPreprocessor):
    """
    Resolve SM_RULE_BRAND_BURGER_WRAPPER_COLOR from PARAM_CUST_BRAND in context.
    NETELLER (uppercase) → "#73a747", otherwise → "#67235e".
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "SM_RULE_BRAND_BURGER_WRAPPER_COLOR":
            brand = (parameters_get_ci(context.parameters, "PARAM_CUST_BRAND") or "").upper()
            color = (
                NETELLER_BURGER_MENU_COLOR_VALUE
                if brand == "NETELLER"
                else DEFAULT_BURGER_MENU_COLOR_VALUE
            )
            context.parameters[SM_RULE_BRAND_BURGER_WRAPPER_COLOR_KEY] = color
            return SM_RULE_BRAND_BURGER_WRAPPER_COLOR_KEY
        return key


class FixedMailingIdPreprocessor(PlaceholderPreprocessor):
    """
    Resolve MAILINGID to a fixed value ("1914").
    Rewrites MAILINGID → __FIXED_MAILINGID__; the value must be in context.parameters.
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        if key == "MAILINGID":
            return FIXED_MAILINGID_KEY
        return key


class NamespacePreprocessor(PlaceholderPreprocessor):
    """
    Rewrite NAMESPACE.SUFFIX → {context_value}.SUFFIX when NAMESPACE is in context.
    E.g. PARAM_CUST_BRAND.BRANDNAME + context["PARAM_CUST_BRAND"]="SKRILL" → SKRILL.BRANDNAME.
    E.g. LANG_LOCAL.SUBJECT_LINE_1 + context["LANG_LOCAL"]="EN" → EN.SUBJECT_LINE_1.
    Applied repeatedly to handle nested namespaces. Keys without a dot are unchanged.
    """

    def process(self, key: str, context: ResolutionContext) -> str:
        while "." in key:
            prefix, _, suffix = key.partition(".")
            namespace_value = parameters_get_ci(context.parameters, prefix)
            if namespace_value is None or not isinstance(namespace_value, str):
                break
            # Graph keys are uppercase; LANG_LOCAL / PARAM_CUST_BRAND often arrive lowercased from
            # callers. Uppercase only these two so e.g. skrill.MONEY_TRANSFER_ACRONYM → SKRILL.*.
            if canonical_placeholder_key(prefix) in ("LANG_LOCAL", "PARAM_CUST_BRAND"):
                namespace_value = namespace_value.upper()
            key = f"{namespace_value}.{suffix}"
        return key

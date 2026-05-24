import re

def normalize_key(raw: str) -> str:
    """Strip placeholder wrapper patterns and uppercase the result.

    Handles: ##KEY##, ##/KEY##, ##//KEY##, ##\\KEY##.
    Keys are case-insensitive at input; output is always uppercase.

    Args:
        raw: Raw placeholder string, with or without ## wrappers.

    Returns:
        Uppercase canonical key string.
    """
    s = raw.upper()
    if s.startswith("##") and s.endswith("##"):
        s = s[2:-2]
    
    # Strip leading slashes and backslashes
    while s.startswith("/") or s.startswith("\\"):
        s = s[1:]
        
    return s

def expand_namespace_prefix(
    canonical_key: str,
    context: dict[str, str],
) -> str:
    """Expand the first dot-segment of a key if it matches a runtime context key.

    Compares the first dot-segment of ``canonical_key`` (case-insensitively) against
    all keys in ``context``. If a match is found and the context value is non-empty,
    replaces the segment with the uppercased context value.

    Args:
        canonical_key: Uppercase key string, e.g. "LANG_LOCAL.PARAGRAPH_1".
        context: Runtime context dict with uppercase keys, e.g. {"LANG_LOCAL": "EN"}.

    Returns:
        Expanded key, e.g. "EN.PARAGRAPH_1". Returns ``canonical_key`` unchanged
        if no prefix match is found or the matched context value is empty.
    """
    if "." not in canonical_key:
        return canonical_key
        
    prefix, rest = canonical_key.split(".", 1)
    
    # context keys are assumed to be uppercase since we are building them uppercase
    if prefix in context:
        val = context[prefix]
        if val:
            return f"{val.upper()}.{rest}"
            
    return canonical_key

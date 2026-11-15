"""Shared canonicalization; this module is part of the frozen source contract."""
from urllib.parse import urlsplit

_HEX = frozenset("0123456789abcdefABCDEF")
_UNRESERVED = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def canonical(text):
    if not isinstance(text, str):
        raise ValueError("expected string")
    try:
        text.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("invalid Unicode") from exc
    out = bytearray()
    i = 0
    while i < len(text):
        c = text[i]
        if c == "%":
            if i + 2 >= len(text) or any(x not in _HEX for x in text[i + 1:i + 3]):
                raise ValueError("bad percent escape")
            value = int(text[i + 1:i + 3], 16)
            if value in _UNRESERVED:
                out.append(value)
            else:
                out.extend(("%" + format(value, "02X")).encode("ascii"))
            i += 3
            continue
        if ord(c) < 33 or ord(c) == 127:
            raise ValueError("control or space")
        if ord(c) < 128:
            out.append(ord(c))
        else:
            for value in c.encode("utf-8"):
                out.extend(("%" + format(value, "02X")).encode("ascii"))
        i += 1
    return bytes(out)


def rule_parts(item):
    if not isinstance(item, (list, tuple)) or len(item) != 2:
        raise ValueError("bad rule")
    action, pattern = item
    if action not in ("allow", "disallow") or not isinstance(pattern, str):
        raise ValueError("bad rule")
    if not pattern:
        return None
    if not pattern.startswith("/"):
        raise ValueError("rule must start with slash")
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    parts = tuple(canonical(piece) for piece in body.split("*"))
    return action == "allow", parts, anchored, sum(map(len, parts))


def url_path(url):
    if not isinstance(url, str):
        raise ValueError("expected URL")
    # Validate the complete input even when the fragment is discarded.
    canonical(url)
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("absolute http(s) URL required")
        parsed.port
    except (ValueError, UnicodeError) as exc:
        raise ValueError("bad URL") from exc
    path = parsed.path or "/"
    # A present empty query still contributes the question mark.
    before_fragment = url.split("#", 1)[0]
    if "?" in before_fragment:
        path += "?" + parsed.query
    return canonical(path)

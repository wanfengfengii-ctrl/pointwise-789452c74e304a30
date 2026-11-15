"""Correct frozen implementation: one regular expression per nonempty rule."""
import re
from normalization import rule_parts, url_path


class Policy:
    def __init__(self, rules):
        if not isinstance(rules, (list, tuple)):
            raise ValueError("rules must be a list or tuple")
        compiled = []
        for item in rules:
            parsed = rule_parts(item)
            if parsed is None:
                continue
            allow, parts, anchored, score = parsed
            expression = b".*".join(re.escape(part) for part in parts)
            expression = b"\\A" + expression + (b"\\Z" if anchored else b"")
            compiled.append((re.compile(expression, re.DOTALL), score, allow))
        self._rules = compiled

    def allowed(self, url):
        path = url_path(url)
        best = (-1, True)
        for expression, score, allow in self._rules:
            if expression.match(path) is not None:
                best = max(best, (score, allow))
        return best[1]

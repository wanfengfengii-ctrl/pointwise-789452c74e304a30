"""Independent differential and boundary checks for the optimized Policy.

Rerun: python3 diffcheck.py

Compares policy.Policy against reference.Policy and a small independent
dynamic-programming judge (no regular expressions) on hand-built boundary
cases and on randomized rule sets, and checks error handling, result
stability after caller-side mutation, and instance isolation.
Exits nonzero on the first mismatch; prints a JSON summary on success.
"""
import json
import random
import sys
from functools import lru_cache

from normalization import rule_parts, url_path
from policy import Policy
from reference import Policy as Reference


def oracle(rules, url):
    """Small dynamic-programming judge, independent of both implementations."""
    path = url_path(url)
    best = (-1, True)
    for item in rules:
        parsed = rule_parts(item)
        if parsed is None:
            continue
        allow, parts, anchored, score = parsed
        tokens = []
        for i, part in enumerate(parts):
            if i:
                tokens.append(None)
            tokens.extend(part)

        @lru_cache(None)
        def match(i, j):
            if i == len(tokens):
                return j == len(path) if anchored else True
            token = tokens[i]
            if token is None:
                return match(i + 1, j) or (j < len(path) and match(i, j + 1))
            return j < len(path) and path[j] == token and match(i + 1, j + 1)

        if match(0, 0):
            best = max(best, (score, allow))
    return best[1]


def check_all(rules, urls, comparisons):
    """Every implementation must agree on every URL."""
    target = Policy(rules)
    reference = Reference(rules)
    for url in urls:
        expected = oracle(rules, url)
        got = target.allowed(url)
        assert got is expected, (rules, url, got, expected)
        assert reference.allowed(url) is expected, (rules, url, "reference", expected)
        # Repeated queries on one instance must be stable.
        assert target.allowed(url) is expected, (rules, url, "unstable")
        comparisons += 1
    return comparisons


def boundary():
    cases = [
        # (rules, urls): empty rules, empty patterns, anchors, wildcards.
        ([], ["https://p.example", "https://p.example/anything"]),
        ([["disallow", ""]], ["https://p.example/", "https://p.example/x"]),
        ([["disallow", "/"]], ["https://p.example", "https://p.example/a"]),
        ([["disallow", "/$"]], ["https://p.example", "https://p.example/"]),
        ([["disallow", "/*"]], ["https://p.example/", "https://p.example/a/b"]),
        ([["disallow", "/*$"]], ["https://p.example/a", "https://p.example/a/b"]),
        ([["disallow", "/**"]], ["https://p.example", "https://p.example/a/b"]),
        ([["disallow", "/**$"]], ["https://p.example", "https://p.example/a/b"]),
        ([["disallow", "/a*$"]], ["https://p.example/a", "https://p.example/a/b/c"]),
        ([["disallow", "/a**b$"], ["allow", "/a*b$"]],
         ["https://p.example/ab", "https://p.example/axxb", "https://p.example/abx"]),
        ([["disallow", "/a*b$"]], ["https://p.example/aXbY", "https://p.example/aXbXb"]),
        ([["disallow", "/aa*aa$"]],
         ["https://p.example/aaa", "https://p.example/aaaa", "https://p.example/aa"]),
        ([["disallow", "/x*/y$"]], ["https://p.example/x/y", "https://p.example/xz/y"]),
        ([["disallow", "/a*/a$"]], ["https://p.example/a/a", "https://p.example/a/b/a"]),
        # '%2A' and '%24' are literal bytes, never meta characters.
        ([["disallow", "/literal%2A$"]],
         ["https://p.example/literal%2a", "https://p.example/literal*"]),
        ([["disallow", "/p%24$"]], ["https://p.example/p%24", "https://p.example/p$"]),
        ([["disallow", "/p$z"]], ["https://p.example/p$z/more", "https://p.example/p"]),
        # Percent-encoded reserved bytes score 3 and stay distinct from '/'.
        ([["disallow", "/x%2Fy$"]],
         ["https://p.example/x%2fy", "https://p.example/x/y"]),
        ([["disallow", "/a%2F"], ["allow", "/a/"]],
         ["https://p.example/a%2F", "https://p.example/a/"]),
        # Unreserved bytes decode before matching, case-insensitive hex.
        ([["disallow", "/~"], ["allow", "/~$"]],
         ["https://p.example/%7e", "https://p.example/~x"]),
        ([["disallow", "/ab*"], ["allow", "/a%62*"]], ["https://p.example/ab"]),
        # Ties between equal scores are won by allow, duplicates are legal.
        ([["disallow", "/dup$"], ["allow", "/dup$"], ["disallow", "/dup$"]],
         ["https://p.example/dup"]),
        ([["allow", "/t*"], ["disallow", "/t*"]], ["https://p.example/t/u"]),
        # Longer literal wins over shorter, regardless of rule order.
        ([["allow", "/s*"], ["disallow", "/s/a*"]],
         ["https://p.example/s/a", "https://p.example/s/b"]),
        ([["disallow", "/s/a*"], ["allow", "/s*"]],
         ["https://p.example/s/a", "https://p.example/s/b"]),
        # Query strings and fragments.
        ([["disallow", "/q?$"], ["allow", "/q$"]],
         ["https://p.example/q", "https://p.example/q?", "https://p.example/q?x=1"]),
        ([["disallow", "/search?token=*"]],
         ["https://p.example/search?token=abc#frag", "https://p.example/search",
          "https://p.example/search?token="]),
        ([["allow", "/f$"]], ["https://p.example/f#only", "https://p.example/f/x#y"]),
        # Non-ASCII canonicalizes to UTF-8 percent triplets.
        ([["disallow", "/caf%C3%A9/*"], ["allow", "/café/public$"]],
         ["https://p.example/café/secret", "https://p.example/caf%C3%A9/public",
          "https://p.example/caf%c3%a9/public"]),
        # Wildcard-only rules match everything with score 0.
        ([["disallow", "/**"], ["allow", "/ok$"]],
         ["https://p.example/ok", "https://p.example/no"]),
        # Port and explicit empty path handling.
        ([["disallow", "/p*"]],
         ["https://p.example:8080/p1", "http://p.example/p"]),
    ]
    comparisons = 0
    for rules, urls in cases:
        comparisons = check_all(rules, urls, comparisons)
    return comparisons


def randomized(rounds=260, urls_per=24, seed=20261115):
    pattern_tokens = ["a", "b", "c", "/", "*", "**", "$", "%2F", "%2f", "%2A",
                      "%24", "%7E", "%7e", "~", "é", "?", "&", "=", "xy"]
    url_tokens = ["a", "b", "c", "/", "$", "*", "%2F", "%2f", "%41", "%2A",
                  "%24", "%7E", "%7e", "~", "é", "xy"]
    rng = random.Random(seed)
    comparisons = 0
    for _ in range(rounds):
        rules = []
        for _ in range(rng.randrange(1, 22)):
            if rng.random() < 0.05:
                rules.append([rng.choice(["allow", "disallow"]), ""])
                continue
            body = "".join(rng.choice(pattern_tokens)
                           for _ in range(rng.randrange(0, 9)))
            rules.append([rng.choice(["allow", "disallow"]), "/" + body])
        urls = []
        for _ in range(urls_per):
            url = "https://p.example/" + "".join(
                rng.choice(url_tokens) for _ in range(rng.randrange(0, 10)))
            if rng.random() < 0.3:
                url += "?" + "".join(rng.choice(["a", "=", "&", "%2F", "$"])
                                     for _ in range(rng.randrange(0, 5)))
            if rng.random() < 0.3:
                url += "#frag"
            urls.append(url)
        comparisons = check_all(rules, urls, comparisons)
    return comparisons


def structured():
    """Shaped loads: shared prefixes and overlapping wildcards, random data."""
    rng = random.Random(407)
    comparisons = 0
    for _ in range(3):
        stem = "/archive/" + "seg/" * rng.randrange(1, 4)
        rules = [[rng.choice(["allow", "disallow"]),
                  stem + format(i, "03x") + "/r$"] for i in range(160)]
        urls = ["https://p.example" + stem + format(rng.randrange(200), "03x") + "/r"
                for _ in range(40)]
        comparisons = check_all(rules, urls, comparisons)
        rules = [[rng.choice(["allow", "disallow"]),
                  "/e/*/s/*/t" + format(i, "03x") + "$"] for i in range(160)]
        rules += [["allow", "/e/*/s/*/t000$"], ["disallow", "/e/**/s/**/t000$"]]
        urls = ["https://p.example/e/a/s/b/s/c/t" + format(rng.randrange(200), "03x")
                for _ in range(40)]
        comparisons = check_all(rules, urls, comparisons)
    return comparisons


def errors_and_isolation():
    bad_rules = [None, {}, "x", 5, [["deny", "/"]], [["allow", "x"]],
                 [["allow", "/%xx"]], [["allow", "/a", 3]], [["allow"]],
                 [["allow", 5]], [["ALLOW", "/"]], [("/a",)]]
    for bad in bad_rules:
        for cls in (Policy, Reference):
            try:
                cls(bad)
            except ValueError:
                pass
            else:
                raise AssertionError(("accepted bad rules", cls, bad))
    obj = Policy([["disallow", "/a*"]])
    ref = Reference([["disallow", "/a*"]])
    bad_urls = [None, 5, "", "/relative", "ftp://p/x", "https://p/%xx",
                "https://p/a b", "https://p:bad/x", "https://p:99999/x",
                "https:///x", "https://p/%"]
    for bad in bad_urls:
        for who in (obj, ref):
            try:
                who.allowed(bad)
            except ValueError:
                pass
            else:
                raise AssertionError(("accepted bad URL", who, bad))
    # A failed query must not poison later ones.
    assert obj.allowed("https://p.example/ab") is False
    assert obj.allowed("https://p.example/ok") is True
    # Mutating the caller's containers must not change decisions.
    rules = [["disallow", "/m*"], ["allow", "/m/ok$"]]
    urls = ["https://p.example/m/1", "https://p.example/m/ok"]
    obj = Policy(rules)
    before = [obj.allowed(u) for u in urls]
    rules[0][1] = "/changed"
    rules.append(["disallow", "/"])
    assert [obj.allowed(u) for u in urls] == before
    # Instances are independent; no cross-instance caching.
    first = Policy([["disallow", "/z*"]])
    second = Policy([["allow", "/z*"]])
    assert first.allowed("https://p.example/z") is False
    assert second.allowed("https://p.example/z") is True
    assert first.allowed("https://p.example/z") is False
    return len(bad_rules) + len(bad_urls) + 5


if __name__ == "__main__":
    if sys.argv[1:]:
        raise SystemExit("no arguments expected")
    total = boundary()
    total += randomized()
    total += structured()
    total += errors_and_isolation()
    print(json.dumps({"comparisons": total, "result": "differential-ok"}))

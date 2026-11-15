import json
import random
import sys
from functools import lru_cache
from policy import Policy
from normalization import rule_parts, url_path
from samples import RULES, CASES


def oracle(rules, url):
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


def verify():
    policy = Policy(RULES)
    for url, expected in CASES:
        assert policy.allowed(url) is expected, (url, expected)
    rules = [
        ["disallow", "/a**b$"], ["allow", "/a*b$"],
        ["disallow", "/literal%2A$"], ["disallow", "/x%2Fy$"],
        ["disallow", "/p$z"], ["disallow", ""],
        ["disallow", "/~"], ["allow", "/~$"],
        ["disallow", "/q?$"], ["allow", "/q$"],
    ]
    urls = ["/ab", "/axxb", "/abx", "/literal%2a", "/literal*",
            "/x%2fy", "/x/y", "/p$z/more", "/%7e", "/~x", "/q", "/q?", "/"]
    obj = Policy(rules)
    for tail in urls:
        url = "https://p.example" + tail
        assert obj.allowed(url) is oracle(rules, url), url
    rng = random.Random(2407)
    alphabet = "ab/*$"
    comparisons = 0
    for unused in range(70):
        group = [[rng.choice(["allow", "disallow"]),
                  "/" + "".join(rng.choices(alphabet, k=rng.randrange(9)))]
                 for other in range(20)]
        obj = Policy(group)
        for other in range(30):
            url = "https://p.example/" + "".join(rng.choices("ab/$", k=rng.randrange(10)))
            assert obj.allowed(url) is oracle(group, url), (group, url)
            comparisons += 1
    for bad in (None, {}, [["deny", "/"]], [["allow", "x"]], [["allow", "/%xx"]]):
        try:
            Policy(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(("accepted bad rules", bad))
    obj = Policy(RULES)
    for bad in (None, "/relative", "ftp://p/x", "https://p/%xx", "https://p/a b", "https://p:bad/x"):
        try:
            obj.allowed(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(("accepted bad URL", bad))
    assert obj.allowed(CASES[0][0]) is True
    assert Policy([]).allowed("https://p.example") is True
    print(json.dumps({"business_cases": len(CASES), "random_comparisons": comparisons,
                      "result": "compatible"}, ensure_ascii=False))


def demo():
    policy = Policy(RULES)
    for url, expected in CASES:
        print(json.dumps({"url": url, "allowed": policy.allowed(url)}, ensure_ascii=False))


if __name__ == "__main__":
    if sys.argv[1:] == ["demo"]:
        demo()
    elif sys.argv[1:] in ([], ["verify"]):
        verify()
    else:
        raise SystemExit("use verify or demo")

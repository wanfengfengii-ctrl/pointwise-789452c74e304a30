RULES = [
    ["disallow", "/private/*"],
    ["allow", "/private/open$"],
    ["disallow", "/caf%C3%A9/*"],
    ["allow", "/café/public$"],
    ["disallow", "/search?token=*"],
]
CASES = [
    ("https://portal.example/private/open", True),
    ("https://portal.example/private/open/x", False),
    ("https://portal.example/café/secret", False),
    ("https://portal.example/caf%C3%A9/public", True),
    ("https://portal.example/search?token=abc#ignored", False),
    ("https://portal.example/notice/7", True),
]

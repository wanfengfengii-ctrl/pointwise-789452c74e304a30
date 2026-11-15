import sys
from checks import verify
from bench import run

if __name__ == "__main__":
    if sys.argv[1:] not in (["baseline"], ["target"]):
        raise SystemExit("use baseline or target")
    verify()
    run(enforce=sys.argv[1] == "target")

"""Frozen loads and assertions. Baseline reports; target enforces optimization."""
import gc
import json
import re
import statistics
import sys
import time
import tracemalloc
from reference import Policy as Reference
from policy import Policy


def workloads():
    prefix = "/archive/" + "shared-segment/" * 6
    rules = [[("allow" if i % 3 == 0 else "disallow"),
              prefix + format(i, "04x") + "/report$"] for i in range(4096)]
    urls = ["https://p.example" + prefix + format((i * 37) % 5120, "04x") + "/report"
            for i in range(192)]
    yield "shared_prefix", rules, urls
    rules = [[("allow" if i % 3 == 0 else "disallow"),
              "/exports/*/shared/*/tag" + format(i, "04x") + "$"] for i in range(4096)]
    # Equal-score allow/disallow rules and consecutive stars must agree.
    rules += [["allow", "/exports/*/shared/*/tag0000$"],
              ["disallow", "/exports/**/shared/**/tag0000$"]]
    urls = ["https://p.example/exports/a/shared/b/shared/c/tag" +
            format((i * 37) % 5120, "04x") for i in range(192)]
    yield "wildcard_overlap", rules, urls


def construct(cls, rules):
    gc.collect()
    re.purge()
    started = time.perf_counter()
    obj = cls(rules)
    return obj, time.perf_counter() - started


def sweep(obj, urls):
    started = time.perf_counter()
    values = [obj.allowed(url) for url in urls]
    return values, time.perf_counter() - started


def run(enforce=False):
    reports = []
    for name, rules, urls in workloads():
        ref_build, target_build = [], []
        ref_query, target_query = [], []
        for repeat in range(3):
            # Alternate order to reduce systematic warmup bias.
            results = {}
            for label, cls in ([("reference", Reference), ("target", Policy)]
                               if repeat % 2 == 0 else
                               [("target", Policy), ("reference", Reference)]):
                obj, build = construct(cls, rules)
                values, elapsed = sweep(obj, urls)
                results[label] = values
                (ref_build if label == "reference" else target_build).append(build)
                (ref_query if label == "reference" else target_query).append(elapsed)
                del obj
            assert results["reference"] == results["target"], name
        gc.collect()
        re.purge()
        tracemalloc.start()
        obj = Policy(rules)
        assert [obj.allowed(url) for url in urls] == results["reference"]
        unused, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        del obj
        rb, tb = statistics.median(ref_build), statistics.median(target_build)
        rq, tq = statistics.median(ref_query), statistics.median(target_query)
        report = {"load": name, "rules": len(rules), "queries": len(urls),
                  "reference_build_s": rb, "target_build_s": tb,
                  "reference_query_s": rq, "target_query_s": tq,
                  "query_ratio": tq / rq, "target_peak_bytes": peak,
                  "reference_build_plus_3_sweeps_s": rb + 3 * rq,
                  "target_build_plus_3_sweeps_s": tb + 3 * tq}
        reports.append(report)
        print(json.dumps(report), flush=True)
        if enforce:
            assert tq <= rq / 5, (name, "query speed")
            assert tb <= 3, (name, "construction")
            assert tb + 3 * tq <= rb + 3 * rq, (name, "total cost")
            assert peak <= 48 * 1024 * 1024, (name, "memory")
    return reports


if __name__ == "__main__":
    if sys.argv[1:] not in ([], ["baseline"], ["target"]):
        raise SystemExit("use baseline or target")
    run(sys.argv[1:] == ["target"])

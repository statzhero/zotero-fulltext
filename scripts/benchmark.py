"""Small benchmark harness for zotero-fulltext."""

from __future__ import annotations

import argparse
import json
from statistics import mean
from time import perf_counter

from zotero_fulltext.service import ZoteroFulltextService


def benchmark_call(callback, runs: int) -> dict[str, float]:
    timings = []
    payload = None
    for _ in range(runs):
        start = perf_counter()
        payload = callback()
        timings.append((perf_counter() - start) * 1000)
    return {
        "runs": runs,
        "mean_ms": round(mean(timings), 3),
        "min_ms": round(min(timings), 3),
        "max_ms": round(max(timings), 3),
        "last_payload_bytes": len(json.dumps(payload).encode("utf-8")) if payload is not None else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark zotero-fulltext calls against a local Zotero library.")
    parser.add_argument("--query", required=True, help="Search query to benchmark.")
    parser.add_argument("--citekey", required=True, help="Citekey to benchmark for lookup/fulltext.")
    parser.add_argument("--runs", type=int, default=5, help="Number of runs per measurement.")
    args = parser.parse_args()

    service = ZoteroFulltextService()
    service.refresh_metadata(force=True)

    cold_lookup = benchmark_call(lambda: service.lookup(args.citekey), 1)
    warm_lookup = benchmark_call(lambda: service.lookup(args.citekey), args.runs)
    search = benchmark_call(lambda: service.search(args.query), args.runs)

    service.paragraph_cache.clear()
    cold_fulltext = benchmark_call(lambda: service.fulltext(args.citekey), 1)
    warm_fulltext = benchmark_call(lambda: service.fulltext(args.citekey), args.runs)

    print(
        json.dumps(
            {
                "query": args.query,
                "citekey": args.citekey,
                "cold_lookup": cold_lookup,
                "warm_lookup": warm_lookup,
                "search": search,
                "cold_fulltext": cold_fulltext,
                "warm_fulltext": warm_fulltext,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

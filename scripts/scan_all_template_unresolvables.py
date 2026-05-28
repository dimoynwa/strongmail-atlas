#!/usr/bin/env python3
"""
Scan every template for unresolvable ##PLACEHOLDER## tokens.

Uses resolution context lang_local=EN and param_cust_brand=SKRILL for every
template. Loads each template body from template_details (one row per template in
production). Resolves HTML and plain-text bodies via the shared resolution engine
and reports per-template and aggregate unresolvable key sets.

Usage:
    PYTHONPATH=. uv run python scripts/scan_all_template_unresolvables.py
    PYTHONPATH=. uv run python scripts/scan_all_template_unresolvables.py --json-out report.json
    PYTHONPATH=. uv run python scripts/scan_all_template_unresolvables.py --approved-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

from shared.config import DATABASE_URL, REDIS_URL
from shared.db import close_pool, init_pool
from shared.redis_client import init_redis
from shared.resolution.graph_builder import build_resolution_graph
from shared.resolution.resolver import UnresolvableEntry
from template_assistant.context import SessionContext
from template_assistant.services import scan_template_unresolvables

LANG_LOCAL = "EN"
PARAM_CUST_BRAND = "SKRILL"
SCAN_SESSION_ID = "scan-all-template-unresolvables"

_ACTIVE_TEMPLATE_STATUSES = ("Approved", "ACTIVE")


@dataclass(frozen=True)
class TemplateScanResult:
    template_name: str
    unresolvables: tuple[UnresolvableEntry, ...]
    error: str | None = None

    @property
    def unresolvable_count(self) -> int:
        return len(self.unresolvables)


def _entry_to_dict(entry: UnresolvableEntry) -> dict[str, str]:
    return {
        "key": entry.key,
        "reason": entry.reason.value,
        "detail": entry.detail,
    }


async def _list_template_names(pool, *, approved_only: bool) -> list[str]:
    async with pool.acquire() as conn:
        if approved_only:
            rows = await conn.fetch(
                """
                SELECT DISTINCT t.name
                FROM template t
                JOIN template_details td ON td.template_id = t.id
                WHERE t.template_status = ANY($1::text[])
                ORDER BY t.name
                """,
                list(_ACTIVE_TEMPLATE_STATUSES),
            )
        else:
            rows = await conn.fetch(
                """
                SELECT DISTINCT t.name
                FROM template t
                JOIN template_details td ON td.template_id = t.id
                ORDER BY t.name
                """,
            )
    return [row["name"] for row in rows]


async def _scan_template(
    pool,
    redis_client,
    template_name: str,
) -> TemplateScanResult:
    del redis_client
    try:
        session_context = SessionContext(
            template_name=template_name,
            lang_local=LANG_LOCAL,
            param_cust_brand=PARAM_CUST_BRAND,
            session_id=SCAN_SESSION_ID,
        )
        graph = await build_resolution_graph(pool, template_name)
        unresolvables, _scan_sources = await scan_template_unresolvables(
            session_context,
            graph=graph,
        )
        return TemplateScanResult(
            template_name=template_name,
            unresolvables=tuple(unresolvables),
        )
    except ValueError as exc:
        return TemplateScanResult(
            template_name=template_name,
            unresolvables=(),
            error=str(exc),
        )
    except Exception as exc:
        return TemplateScanResult(
            template_name=template_name,
            unresolvables=(),
            error=f"{type(exc).__name__}: {exc}",
        )


async def run_scan(*, approved_only: bool, limit: int | None) -> dict:
    pool = await init_pool(DATABASE_URL)
    redis_client = await init_redis(REDIS_URL)

    try:
        names = await _list_template_names(pool, approved_only=approved_only)
        if limit is not None:
            names = names[:limit]

        results: list[TemplateScanResult] = []
        for i, name in enumerate(names, start=1):
            result = await _scan_template(pool, redis_client, name)
            results.append(result)
            if i % 25 == 0 or i == len(names):
                print(f"Scanned {i}/{len(names)} templates...", file=sys.stderr)

        aggregate_keys: set[str] = set()
        templates_with_issues = 0
        templates_with_errors = 0
        payload_results = []

        for result in results:
            if result.error:
                templates_with_errors += 1
            if result.unresolvables:
                templates_with_issues += 1
                aggregate_keys.update(e.key for e in result.unresolvables)

            payload_results.append(
                {
                    "template_name": result.template_name,
                    "unresolvable_count": result.unresolvable_count,
                    "error": result.error,
                    "unresolvables": [_entry_to_dict(e) for e in result.unresolvables],
                }
            )

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "context": {
                "lang_local": LANG_LOCAL,
                "param_cust_brand": PARAM_CUST_BRAND,
                "session_id": SCAN_SESSION_ID,
            },
            "filters": {"approved_only": approved_only, "limit": limit},
            "templates_scanned": len(results),
            "templates_with_unresolvables": templates_with_issues,
            "templates_with_errors": templates_with_errors,
            "aggregate_unique_unresolvable_keys": sorted(aggregate_keys),
            "aggregate_unique_key_count": len(aggregate_keys),
            "results": payload_results,
        }
    finally:
        await close_pool()
        await redis_client.aclose()


def _print_summary(report: dict) -> None:
    ctx = report["context"]
    print(
        f"Context: lang_local={ctx['lang_local']}, param_cust_brand={ctx['param_cust_brand']}"
    )
    print(f"Templates scanned: {report['templates_scanned']}")
    print(f"Templates with unresolvables: {report['templates_with_unresolvables']}")
    print(f"Templates with errors: {report['templates_with_errors']}")
    print(f"Unique unresolvable keys (aggregate): {report['aggregate_unique_key_count']}")

    failing = [
        r
        for r in report["results"]
        if r["unresolvable_count"] > 0 or r.get("error")
    ]
    failing.sort(key=lambda r: (-r["unresolvable_count"], r["template_name"]))

    print("\nTemplates with issues:")
    for row in failing:
        if row.get("error"):
            print(f"  {row['template_name']}: ERROR — {row['error']}")
            continue
        keys = ", ".join(u["key"] for u in row["unresolvables"][:8])
        extra = "" if row["unresolvable_count"] <= 8 else f" (+{row['unresolvable_count'] - 8} more)"
        print(f"  {row['template_name']}: {row['unresolvable_count']} — {keys}{extra}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find unresolvable placeholders for all templates (EN / SKRILL)."
    )
    parser.add_argument(
        "--approved-only",
        action="store_true",
        help="Only templates with status Approved or ACTIVE.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after N templates (for testing).",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default=None,
        help="Write full JSON report to this path.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress human-readable summary on stdout.",
    )
    args = parser.parse_args()

    report = asyncio.run(
        run_scan(approved_only=args.approved_only, limit=args.limit)
    )

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            f.write("\n")
        print(f"Wrote JSON report to {args.json_out}", file=sys.stderr)

    if not args.quiet:
        _print_summary(report)


if __name__ == "__main__":
    main()

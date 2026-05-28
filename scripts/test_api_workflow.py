#!/usr/bin/env python3
"""Run all Agent Studio API endpoints in workflow order."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field

import httpx

from shared.config import DATABASE_URL
from shared.db import close_pool, init_pool
from shared.resolution.graph_builder import build_resolution_graph

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 120.0
CHAT_TIMEOUT = 180.0


async def _pick_graph_key(template_name: str) -> str:
    pool = await init_pool(DATABASE_URL)
    try:
        graph = await build_resolution_graph(pool, template_name)
        for key in sorted(graph.keys()):
            value = graph[key]
            if (
                len(value) >= 20
                and not value.startswith("http")
                and not key.endswith(("_URL", "_COLOR", "_ID"))
            ):
                return key
        return sorted(graph.keys())[0]
    finally:
        await close_pool()


def pick_graph_key(template_name: str) -> str:
    return asyncio.run(_pick_graph_key(template_name))


@dataclass
class StepResult:
    name: str
    method: str
    path: str
    status: int | None
    ok: bool
    detail: str = ""
    elapsed_ms: int = 0


@dataclass
class RunReport:
    results: list[StepResult] = field(default_factory=list)
    session_id: str = ""
    template_name: str = "NFY_SM_REGISTERED"
    wc_key: str = ""

    def add(self, result: StepResult) -> None:
        self.results.append(result)
        icon = "PASS" if result.ok else "FAIL"
        print(f"[{icon}] {result.method} {result.path} -> {result.status} ({result.elapsed_ms}ms)")
        if result.detail:
            print(f"       {result.detail}")

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)


def _request(
    client: httpx.Client,
    report: RunReport,
    name: str,
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    params: dict | None = None,
    expect: int | tuple[int, ...] = 200,
    timeout: float = TIMEOUT,
) -> httpx.Response | None:
    start = time.perf_counter()
    try:
        response = client.request(
            method,
            f"{BASE_URL}{path}",
            json=json_body,
            params=params,
            timeout=timeout,
        )
        elapsed = int((time.perf_counter() - start) * 1000)
        expected = (expect,) if isinstance(expect, int) else expect
        ok = response.status_code in expected
        detail = ""
        if not ok:
            detail = response.text[:300]
        report.add(
            StepResult(name, method, path, response.status_code, ok, detail, elapsed)
        )
        return response if ok else None
    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        report.add(
            StepResult(name, method, path, None, False, str(exc)[:300], elapsed)
        )
        return None


def _read_sse(client: httpx.Client, report: RunReport, name: str, path: str, body: dict) -> None:
    start = time.perf_counter()
    try:
        event_types: list[str] = []
        with client.stream(
            "POST",
            f"{BASE_URL}{path}",
            json=body,
            headers={"Accept": "text/event-stream"},
            timeout=CHAT_TIMEOUT,
        ) as response:
            if response.status_code != 200:
                text = response.read().decode()[:300]
                elapsed = int((time.perf_counter() - start) * 1000)
                report.add(
                    StepResult(name, "POST", path, response.status_code, False, text, elapsed)
                )
                return
            for line in response.iter_lines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        event_types.append(event.get("type", "?"))
                        if event.get("type") in ("final", "error"):
                            break
                    except json.JSONDecodeError:
                        pass
        elapsed = int((time.perf_counter() - start) * 1000)
        ok = "final" in event_types or "error" in event_types
        detail = f"events={event_types[-5:]}" if event_types else "no SSE events"
        report.add(
            StepResult(name, "POST", path, 200, ok, detail, elapsed)
        )
    except Exception as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        report.add(
            StepResult(name, "POST", path, None, False, str(exc)[:300], elapsed)
        )


def run() -> int:
    report = RunReport()

    with httpx.Client() as client:
        # 1. Health
        health = _request(client, report, "health", "GET", "/health")
        if health:
            data = health.json()
            report.add(
                StepResult(
                    "health-summary",
                    "GET",
                    "/health",
                    200,
                    data.get("status") in ("ok", "degraded"),
                    f"status={data.get('status')}",
                )
            )

        # 2. Template discovery
        templates_resp = _request(client, report, "templates", "GET", "/templates")
        if templates_resp:
            data = templates_resp.json()
            total = data.get("total", 0)
            report.add(
                StepResult(
                    "templates-count",
                    "GET",
                    "/templates",
                    200,
                    total > 0,
                    f"total={total}",
                )
            )
            if data.get("templates"):
                preferred = next(
                    (
                        t["name"]
                        for t in data["templates"]
                        if "NFY_SM_REGISTERED" in t["name"]
                    ),
                    data["templates"][0]["name"],
                )
                report.template_name = preferred

        _request(client, report, "locales", "GET", "/templates/locales")
        _request(client, report, "brands", "GET", "/templates/brands")

        # 3. Session
        session_resp = _request(
            client,
            report,
            "create-session",
            "POST",
            "/session",
            json_body={
                "template_name": report.template_name,
                "lang_local": "EN",
                "param_cust_brand": "SKRILL",
            },
            expect=201,
        )
        if not session_resp:
            print("\nAborting: session creation failed.")
            return 1
        report.session_id = session_resp.json()["session_id"]
        print(f"       session_id={report.session_id} template={report.template_name}")

        sid = report.session_id

        # 4. Initial state
        _request(client, report, "get-working-copy", "GET", f"/working-copy/{sid}")
        _request(
            client,
            report,
            "get-preview",
            "GET",
            f"/preview/{sid}",
            params={"highlight_modified": "true"},
        )

        # 5. Tone
        _request(client, report, "tone-stored", "GET", f"/tone/stored/{sid}")
        _request(
            client,
            report,
            "tone-evaluate",
            "POST",
            f"/tone/evaluate/{sid}",
            json_body={"top_n": 5},
        )

        # 6. Chat (may fail/slow if LLM unavailable)
        _read_sse(
            client,
            report,
            "chat-template",
            "/chat/stream",
            {
                "message": "What is the subject line of this template?",
                "session_id": sid,
                "agent": "template",
            },
        )
        _read_sse(
            client,
            report,
            "chat-general",
            "/chat/stream",
            {
                "message": "List one template related to password reset.",
                "agent": "general",
            },
        )

        # 7. Tone apply (may apply 0 if no pending suggestions)
        apply_resp = _request(
            client,
            report,
            "tone-apply-all",
            "POST",
            f"/tone/apply/{sid}",
            json_body={},
        )
        if apply_resp:
            applied = apply_resp.json().get("applied", 0)
            report.add(
                StepResult(
                    "tone-apply-result",
                    "POST",
                    f"/tone/apply/{sid}",
                    200,
                    True,
                    f"applied={applied}",
                )
            )

        # 8. Verify after apply
        _request(client, report, "get-working-copy-2", "GET", f"/working-copy/{sid}")
        _request(
            client,
            report,
            "get-preview-2",
            "GET",
            f"/preview/{sid}",
            params={"highlight_modified": "true"},
        )
        _request(
            client,
            report,
            "tone-evaluate-2",
            "POST",
            f"/tone/evaluate/{sid}",
            json_body={"top_n": 5},
        )

        # 9. Undo tone
        undo_resp = _request(
            client,
            report,
            "tone-undo-all",
            "POST",
            f"/tone/undo/{sid}",
            json_body={},
        )
        if undo_resp:
            restored = undo_resp.json().get("restored", 0)
            report.add(
                StepResult(
                    "tone-undo-result",
                    "POST",
                    f"/tone/undo/{sid}",
                    200,
                    True,
                    f"restored={restored}",
                )
            )

        # 10. Manual WC patch
        patch_key = pick_graph_key(report.template_name)
        _request(
            client,
            report,
            "patch-working-copy",
            "PATCH",
            f"/working-copy/{sid}",
            json_body={
                "key": patch_key,
                "value": "API test override — please ignore this text",
            },
        )

        # 11. Export
        export = _request(
            client,
            report,
            "export-working-copy",
            "GET",
            f"/working-copy/{sid}/export",
        )
        if export:
            report.add(
                StepResult(
                    "export-check",
                    "GET",
                    f"/working-copy/{sid}/export",
                    200,
                    "exported_at" in export.json(),
                    f"keys={len(export.json().get('overrides', {}))}",
                )
            )

        # 12. Cleanup
        _request(client, report, "delete-working-copy", "DELETE", f"/working-copy/{sid}")

    print()
    print(f"Results: {report.passed} passed, {report.failed} failed (of {len(report.results)} checks)")
    if report.failed:
        print("\nFailures:")
        for r in report.results:
            if not r.ok:
                print(f"  - {r.name}: {r.method} {r.path} ({r.detail})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())

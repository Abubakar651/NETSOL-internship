"""Explicit live Gemini & Groq verification against INC-409. Never runs automatically on startup."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omniops.mcp import OmniOpsMCPServer

from .config import PROJECT_ROOT, Settings, load_settings
from .runner import InvestigationRunner


async def _run_single_provider_check(
    name: str,
    settings: Settings,
    *,
    incident_id: str = "INC-409",
    expected_provider: str,
) -> dict[str, Any]:
    mcp = OmniOpsMCPServer.from_seeded_database()
    try:
        runner = InvestigationRunner(mcp, settings=settings)
        t0 = time.perf_counter()
        result = await runner.investigate(incident_id=incident_id, prefer_offline=False)
        elapsed_s = round(time.perf_counter() - t0, 2)

        report = result.report
        passed = (
            result.provider_used == expected_provider
            and report.answerable is True
            and report.culprit_pull_request_id == "PR-882"
            and report.blast_radius_severity_score == 30
            and report.staged_action_type == "TriggerSafeRollback"
        )
        return {
            "check": name,
            "expected_provider": expected_provider,
            "provider_used": result.provider_used,
            "model": (
                settings.gemini_model
                if expected_provider == "gemini"
                else settings.groq_reasoning_model
            ),
            "status": "passed" if passed else "failed",
            "elapsed_seconds": elapsed_s,
            "incident_id": report.incident_id,
            "primary_failing_service_id": report.primary_failing_service_id,
            "culprit_pull_request_id": report.culprit_pull_request_id,
            "affected_downstream_resource_id": report.affected_downstream_resource_id,
            "blast_radius_severity_score": report.blast_radius_severity_score,
            "staged_branch_name": report.staged_branch_name,
            "staged_action_type": report.staged_action_type,
            "tool_calls": len(result.tool_trace),
            "diagnostic_events": result.diagnostic_events,
        }
    finally:
        mcp.close()


async def run_live_checks(
    *,
    gemini_only: bool = False,
    groq_only: bool = False,
    model_override: str | None = None,
    save_report: bool = False,
) -> tuple[int, dict[str, Any]]:
    base = load_settings()
    if model_override:
        base = replace(base, gemini_model=model_override)

    checks: list[dict[str, Any]] = []

    if not groq_only:
        if not base.gemini_key:
            checks.append(
                {
                    "check": "live_gemini_inc_409",
                    "expected_provider": "gemini",
                    "status": "skipped",
                    "reason": "GEMINI_API_KEY not configured in .env",
                }
            )
        else:
            gem_settings = replace(base, groq_key="", openrouter_key="")
            res = await _run_single_provider_check(
                "live_gemini_inc_409", gem_settings, expected_provider="gemini"
            )
            if res["status"] != "passed" and not model_override and gem_settings.gemini_model != "gemini-3.1-flash-lite":
                # Retry once with gemini-3.1-flash-lite if primary model hit transient 429/503/timeout
                diag_statuses = {d.get("status") for d in res.get("diagnostic_events", [])}
                if diag_statuses & {429, 503, 504, None}:
                    retry_settings = replace(gem_settings, gemini_model="gemini-3.1-flash-lite")
                    retry_res = await _run_single_provider_check(
                        "live_gemini_inc_409", retry_settings, expected_provider="gemini"
                    )
                    retry_res["fallback_from_model"] = gem_settings.gemini_model
                    res = retry_res
            checks.append(res)

    if not gemini_only:
        if not base.groq_key:
            checks.append(
                {
                    "check": "live_groq_inc_409",
                    "expected_provider": "groq",
                    "status": "skipped",
                    "reason": "GROQ_API_KEY not configured in .env",
                }
            )
        else:
            groq_settings = replace(base, gemini_key="", openrouter_key="")
            res = await _run_single_provider_check(
                "live_groq_inc_409", groq_settings, expected_provider="groq"
            )
            checks.append(res)

    summary = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "incident_id": "INC-409",
        "checks": checks,
    }

    if save_report:
        docs_dir = PROJECT_ROOT / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        json_path = docs_dir / "LIVE_PROVIDER_CHECK.json"
        md_path = docs_dir / "LIVE_PROVIDER_CHECK.md"
        json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        lines = [
            "# Live Cloud Provider Verification (`INC-409`)",
            "",
            f"- **Checked At (UTC):** `{summary['checked_at_utc']}`",
            "- **Secrets Policy:** All API keys read locally from untracked `.env`; zero keys stored or printed.",
            "",
            "| Check | Provider | Model | Status | Elapsed | Culprit PR | Blast Score | Staged Action |",
            "| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :--- |",
        ]
        for c in checks:
            lines.append(
                f"| `{c['check']}` | `{c.get('provider_used', c.get('expected_provider'))}` | "
                f"`{c.get('model', '—')}` | **{c['status'].upper()}** | "
                f"{c.get('elapsed_seconds', '—')} s | `{c.get('culprit_pull_request_id', '—')}` | "
                f"{c.get('blast_radius_severity_score', '—')} | `{c.get('staged_action_type', '—')}` |"
            )
        lines.extend(["", "See [`LIVE_PROVIDER_CHECK.json`](LIVE_PROVIDER_CHECK.json) for redacted diagnostics."])
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    all_passed = bool(checks) and all(c["status"] == "passed" for c in checks)
    return (0 if all_passed else 1), summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--gemini-only", action="store_true", help="Verify only Gemini Interactions API.")
    mode.add_argument("--groq-only", action="store_true", help="Verify only Groq Chat Completions API.")
    parser.add_argument("--model", help="Override Gemini model ID without editing .env.")
    parser.add_argument("--save-report", action="store_true", help="Write docs/LIVE_PROVIDER_CHECK.{json,md}.")
    args = parser.parse_args()

    code, summary = asyncio.run(
        run_live_checks(
            gemini_only=args.gemini_only,
            groq_only=args.groq_only,
            model_override=args.model,
            save_report=args.save_report,
        )
    )
    print(json.dumps(summary, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

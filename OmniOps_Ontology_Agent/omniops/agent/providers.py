"""Resilient 3-tier reasoning provider cascade: Gemini -> Groq/OpenRouter -> Offline Ontology Reasoner."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

import httpx

from .config import Settings, redact_secrets
from .prompts import (
    SRE_INVESTIGATION_SYSTEM_PROMPT,
    InvestigationReport,
    investigation_report_json_schema,
)
from .validator import EvidenceValidationError


class ProviderCallError(RuntimeError):
    """Raised when an upstream LLM provider call fails or returns unusable output."""


def _parse_json_output(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Model output JSON must be an object.")
    return parsed


class ReasoningProviders:
    """Async multi-provider reasoning adapter with deterministic offline fallback and key redaction."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.diagnostic_events: list[dict[str, Any]] = []

    def _record_diagnostic(self, provider: str, status: int | None, message: str) -> None:
        self.diagnostic_events.append(
            {
                "provider": provider,
                "status": status,
                "message": redact_secrets(message, self.settings)[:500],
            }
        )

    async def _post_json(
        self,
        provider: str,
        url: str,
        *,
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=self.settings.timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = await client.post(url, headers=headers, json=body)
        except (TimeoutError, httpx.TimeoutException) as exc:
            self._record_diagnostic(provider, 504, f"Request timed out: {exc}")
            raise ProviderCallError(f"{provider} request timed out.") from exc
        except httpx.RequestError as exc:
            self._record_diagnostic(provider, None, f"Network error: {exc}")
            raise ProviderCallError(f"{provider} network error.") from exc

        if not response.is_success:
            try:
                err_json = response.json()
            except ValueError:
                err_json = {}
            msg = (
                err_json.get("error", {}).get("message")
                if isinstance(err_json, dict) and isinstance(err_json.get("error"), dict)
                else response.text
            )
            self._record_diagnostic(provider, response.status_code, str(msg or "Upstream error"))
            raise ProviderCallError(f"{provider} returned HTTP {response.status_code}.")

        try:
            return response.json()
        except ValueError as exc:
            self._record_diagnostic(provider, response.status_code, "Unreadable JSON response.")
            raise ProviderCallError(f"{provider} returned invalid JSON.") from exc

    async def call_gemini(self, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        generation: dict[str, Any] = {"temperature": 0.2, "max_output_tokens": 4096}
        if re.match(r"^gemini-[34]", self.settings.gemini_model):
            generation.update(thinking_level="low", thinking_summaries="none")
        data = await self._post_json(
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.settings.gemini_key,
                "Api-Revision": "2026-05-20",
            },
            body={
                "model": self.settings.gemini_model,
                "store": False,
                "system_instruction": SRE_INVESTIGATION_SYSTEM_PROMPT,
                "input": json.dumps(payload),
                "response_format": {
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": schema,
                },
                "generation_config": generation,
            },
        )
        try:
            if data.get("status") != "completed":
                raise ValueError("Incomplete Gemini interaction")
            content = "".join(
                part.get("text", "")
                for step in data["steps"]
                if step.get("type") == "model_output"
                for part in step.get("content", [])
                if part.get("type") == "text"
            )
            return _parse_json_output(content)
        except (KeyError, TypeError, ValueError) as exc:
            self._record_diagnostic("gemini", 502, f"Unreadable Gemini output: {exc}")
            raise ProviderCallError("Gemini returned unreadable structured output.") from exc

    async def call_chat_completions(
        self,
        provider: str,
        *,
        url: str,
        api_key: str,
        model: str,
        payload: dict[str, Any],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        data = await self._post_json(
            provider,
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": model,
                "messages": [
                    {"role": "system", "content": SRE_INVESTIGATION_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload)},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "omniops_investigation", "strict": True, "schema": schema},
                },
                "temperature": 0.2,
                "max_completion_tokens": 4096,
            },
        )
        try:
            choice = data["choices"][0]
            if choice.get("finish_reason") not in (None, "stop"):
                raise ValueError(f"Unexpected finish_reason={choice.get('finish_reason')}")
            return _parse_json_output(choice["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            self._record_diagnostic(provider, 502, f"Unreadable {provider} output: {exc}")
            raise ProviderCallError(f"{provider} returned unreadable structured output.") from exc

    @staticmethod
    def offline_ontology_reasoner(payload: dict[str, Any]) -> dict[str, Any]:
        """Deterministic graph-grounded fallback synthesizer requiring zero external LLM calls."""
        inc = payload["incident"]
        svc = payload["service"]
        br = payload["blast_radius"]
        suspects = payload["suspect_deployments"]
        downstream_db = payload.get("downstream_db")
        staged = payload.get("staged_action")

        upstream_ids = [item["service_id"] for item in br["impacted_upstream_services"]]
        top_pr = suspects["suspect_deployments"][0] if suspects["suspect_deployments"] else None
        culprit_pr_id = top_pr["pr_id"] if top_pr else None
        db_id = downstream_db["object_id"] if downstream_db else None

        evidence_chain: list[str] = [
            f"Incident {inc['id']} ({inc['severity']}) directly affects {svc['id']} ({svc['name']}, status={svc['status']}, version={svc['current_version']}).",
            f"Upstream blast radius identified {len(upstream_ids)} impacted service(s) ({', '.join(upstream_ids) or 'none'}) with certified severity score {br['blast_radius_severity_score']}.",
        ]
        if downstream_db:
            details = downstream_db.get("details", {})
            if "active_connections" in details and "max_connections" in details:
                evidence_chain.append(
                    f"Downstream resource {db_id} ({downstream_db['name']}) reports {details['active_connections']}/{details['max_connections']} connections (saturation={details.get('connection_saturation_ratio')})."
                )
            else:
                evidence_chain.append(
                    f"Downstream resource {db_id} ({downstream_db['name']}) status is {downstream_db['status']}."
                )
        if top_pr:
            evidence_chain.append(
                f"Deployment correlation ranked {top_pr['pr_id']} ('{top_pr['title']}') #1 with score {top_pr['suspect_score']} ({top_pr['minutes_before_incident']}m prior to {inc['id']})."
            )
        if staged:
            evidence_chain.append(
                f"Staged {staged['action_type']} on isolated branch '{staged['branch_name']}' (commit {staged['commit_hash']}) pending HumanSRE merge approval."
            )

        summary_parts = [
            f"{inc['id']} on {svc['id']} impacts {len(upstream_ids)} upstream service(s) (blast-radius score {br['blast_radius_severity_score']})."
        ]
        if top_pr:
            summary_parts.append(
                f"Root cause traces to {top_pr['pr_id']} ({top_pr['title']}), deployed to {top_pr['target_service_id']}."
            )
        if db_id:
            summary_parts.append(f"Downstream pressure observed on {db_id}.")
        if staged:
            summary_parts.append(
                f"Remediation {staged['action_type']} is staged on branch '{staged['branch_name']}' for human approval."
            )

        return {
            "incident_id": inc["id"],
            "answerable": True,
            "root_cause_summary": " ".join(summary_parts),
            "primary_failing_service_id": svc["id"],
            "culprit_pull_request_id": culprit_pr_id,
            "affected_downstream_resource_id": db_id,
            "upstream_blast_radius_service_ids": upstream_ids,
            "blast_radius_severity_score": br["blast_radius_severity_score"],
            "evidence_chain": evidence_chain,
            "staged_branch_name": staged["branch_name"] if staged else "",
            "staged_action_type": staged["action_type"] if staged else "",
            "staged_commit_hash": staged["commit_hash"] if staged else "",
            "human_approval_required": bool(
                staged["policy_decision"]["requires_human_merge"] if staged else False
            ),
        }

    async def synthesize_report(
        self,
        payload: dict[str, Any],
        validate_fn: Callable[[dict[str, Any]], InvestigationReport],
        *,
        prefer_offline: bool = False,
    ) -> tuple[InvestigationReport, str]:
        """Try Gemini -> Groq -> OpenRouter with corrective evidence retry, then offline fallback."""
        schema = investigation_report_json_schema()

        if not prefer_offline:
            cloud_attempts: list[tuple[str, Callable[[dict[str, Any]], Any]]] = []
            if self.settings.gemini_key:
                cloud_attempts.append(("gemini", lambda p: self.call_gemini(p, schema)))
            if self.settings.groq_key:
                cloud_attempts.append(
                    (
                        "groq",
                        lambda p: self.call_chat_completions(
                            "groq",
                            url="https://api.groq.com/openai/v1/chat/completions",
                            api_key=self.settings.groq_key,
                            model=self.settings.groq_reasoning_model,
                            payload=p,
                            schema=schema,
                        ),
                    )
                )
            if self.settings.openrouter_key:
                cloud_attempts.append(
                    (
                        "openrouter",
                        lambda p: self.call_chat_completions(
                            "openrouter",
                            url="https://openrouter.ai/api/v1/chat/completions",
                            api_key=self.settings.openrouter_key,
                            model=self.settings.openrouter_model,
                            payload=p,
                            schema=schema,
                        ),
                    )
                )

            for provider_name, caller in cloud_attempts:
                hint: str | None = None
                for attempt in range(2):
                    request_payload = (
                        payload
                        if hint is None
                        else {"evidence": payload, "validation_hint": hint}
                    )
                    try:
                        raw_dict = await caller(request_payload)
                        report = validate_fn(raw_dict)
                        return report, provider_name
                    except EvidenceValidationError as exc:
                        self._record_diagnostic(provider_name, 422, f"Attempt {attempt + 1}: {exc}")
                        if attempt == 0:
                            hint = exc.validation_hint
                            continue
                        break
                    except ProviderCallError:
                        break

        offline_raw = self.offline_ontology_reasoner(payload)
        return validate_fn(offline_raw), "offline_ontology_reasoner"

---
phase: 3
step: "3.12"
title: "Domain tools II: licence/fit check & cost estimator"
summary: The licence_fit_check tool (A2 compliance and rider-fit rules with pass/fail/unknown verdicts citing the numbers used) and the cost_estimator tool (versioned coefficient table, self-labelled estimate with visible assumptions).
effort: 3
dependencies: ["3.11"]
---

# Step 3.12 — Domain tools II

**Effort: 3** — two tools on the established convention; the fit rules and
cost heuristics carry the only real logic.

Binding contract: `docs/roadmap/stage-01/phase-3/shared-knowledge.md` (§Tool result
schemas). Agent: **backend-dev**.

## Outline

- `tools/licence_fit_check.py` + `backend/app/services/fit_check_service.py`:
  A2 compliance (≤ 35 kW; power/weight ≤ 0.2 kW/kg — consistent with the
  2.1 `_resolve_a2_eligible` derivation; restricted-version note where
  derivable) and rider fit (seat height vs rider height/inseam bands, bike
  weight vs experience level). Result = the pinned `{rules: [{rule, label,
  verdict, evidence}]}` shape — verdict `pass|fail|unknown` per rule with
  the numbers used composed into `evidence` (server-side English, rendered
  verbatim); missing verified specs yield `unknown`, **never a guessed
  value**.
- `tools/cost_estimator.py` + `backend/app/services/cost_estimator_service.py`
  + `backend/app/services/cost_data.py`: total-cost-of-ownership from the
  verified price band plus a **versioned coefficient table**
  (`COEFFICIENTS_VERSION`, insurance class / consumption / maintenance
  heuristics — a Python constant, not config, no external pricing API).
  Result = the pinned `{lineItems, total, currency: "EUR", assumptions,
  coefficientsVersion}` shape — it labels itself an estimate.
- Both registered in `build_advisor_tools`; both invocable via
  `app tools run`.
- Tests: A2 boundaries (35.0 kW exactly → pass; ratio exactly 0.2 → pass),
  missing spec → `unknown` with reason, estimator determinism (same input,
  same numbers), assumptions non-empty.

## Verification

- `docker compose exec app-web app tools run licence_fit_check --args
  '{"motorbikeName":"Honda CB500F","licence":"A2","riderHeightCm":165}'`
  returns a structured verdict citing verified power/weight figures;
  `cost_estimator` on the same bike returns line items + total + assumptions.

## Risks / notes

- Cost heuristics can look authoritative — the `assumptions` field and the
  UI's Estimate chip are the mitigation; sanity-check the coefficient table
  once against a real-world example before merging.

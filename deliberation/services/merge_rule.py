"""
Consensus Arbiter — Rule-Based Merge for Multi-Agent Opinions

This module is NOT creative. It applies deterministic rules to merge
3-model multi-agent opinions into a single consensus result.

Rules:
  - Numeric fields: weighted median (not average) per field-wise weights
  - Risk scores: upper median or max
  - do_not_damage: union of all models
  - Objective labels: 2/3 majority vote, structure_guard veto on flattening
  - Minority opinions preserved in unresolved_tensions
  - Contradiction detection with severity scoring

Input: list of agent opinions (from deliberation._query_agent)
Output: merged formplan + arbiter report
"""

import json
import logging
from typing import Any

logger = logging.getLogger("deliberation.merge_rule")


# ══════════════════════════════════════════
# Public API
# ══════════════════════════════════════════
def arbitrate(
    opinions: list[dict],
    raw_analysis: dict,
) -> dict:
    """Rule-based merge of multi-agent opinions into consensus formplan.

    Args:
        opinions: list of agent opinion dicts, each containing:
            - agent_key, agent_name, vendor, model, weight
            - field_weights: {macro_form, whole_track_targets, section_targets, ...}
            - formplan: the agent's proposed formplan dict
        raw_analysis: the raw audio analysis dict (ground truth)

    Returns:
        {
            "formplan": merged formplan,
            "arbiter_report": {
                "merge_log": [...],
                "contradictions": [...],
                "vetoes_applied": [...],
                "field_winners": {...},
            }
        }
    """
    if not opinions:
        raise ValueError("Cannot arbitrate with zero opinions")

    merge_log: list[dict] = []
    contradictions: list[dict] = []
    vetoes: list[dict] = []
    field_winners: dict[str, str] = {}

    whole_metrics = raw_analysis.get("whole_track_metrics", {})

    # ── 1. whole_track_targets (weighted median per field weight) ──
    wt_winner = _field_winner(opinions, "whole_track_targets")
    field_winners["whole_track_targets"] = f"{wt_winner['agent_key']}/{wt_winner['vendor']}"

    merged_targets, target_log = _merge_numeric_field(
        opinions, "whole_track_targets", "whole_track_targets",
    )
    merge_log.extend(target_log)

    # Risk targets: use upper median (max of weighted median and individual max)
    risk_keys = [k for k in merged_targets if "risk" in k or "max_" in k]
    for rk in risk_keys:
        vals = []
        for op in opinions:
            v = op["formplan"].get("whole_track_targets", {}).get(rk)
            if v is not None and isinstance(v, (int, float)):
                vals.append(v)
        if vals:
            upper = max(vals)
            if merged_targets.get(rk) is not None and upper > merged_targets[rk]:
                merge_log.append({
                    "field": f"whole_track_targets.{rk}",
                    "rule": "risk_upper_median",
                    "original": merged_targets[rk],
                    "adjusted": upper,
                })
                merged_targets[rk] = upper

    # Compute deltas
    merged_deltas = {}
    for key, target_val in merged_targets.items():
        metric_key = key.replace("target_", "")
        if metric_key.startswith("max_"):
            continue
        current_val = whole_metrics.get(metric_key)
        if current_val is not None and isinstance(current_val, (int, float)):
            merged_deltas[f"{metric_key}_delta"] = round(target_val - current_val, 4)

    # ── 2. macro_form (structural winner) ──
    macro_winner = _field_winner(opinions, "macro_form")
    field_winners["macro_form"] = f"{macro_winner['agent_key']}/{macro_winner['vendor']}"
    merged_macro = _deep_copy_json(macro_winner["formplan"].get("macro_form", {}))

    # Merge section_targets within sections
    if "sections" in merged_macro:
        merged_macro["sections"] = _merge_sections(opinions, merged_macro["sections"], merge_log)

    # ── 3. do_not_damage: union ──
    all_dnd = _collect_do_not_damage(opinions)
    if "sections" in merged_macro:
        for sec in merged_macro["sections"]:
            existing = set(sec.get("do_not_damage", []))
            sec["do_not_damage"] = sorted(existing | all_dnd)
    merge_log.append({
        "field": "do_not_damage",
        "rule": "union_all_models",
        "count": len(all_dnd),
        "items": sorted(all_dnd),
    })

    # ── 4. transition_logic (structural winner) ──
    trans_winner = _field_winner(opinions, "transition_logic")
    field_winners["transition_logic"] = f"{trans_winner['agent_key']}/{trans_winner['vendor']}"
    merged_transitions = trans_winner["formplan"].get("transition_logic", [])

    # ── 5. failure_conditions (union + structure_guard veto) ──
    merged_strategy, fc_vetoes = _merge_failure_conditions(opinions)
    vetoes.extend(fc_vetoes)
    fc_winner = _field_winner(opinions, "failure_conditions")
    field_winners["failure_conditions"] = f"{fc_winner['agent_key']}/{fc_winner['vendor']}"

    # ── 6. Objective labels: 2/3 majority ──
    label_contradictions = _check_label_majority(opinions)
    contradictions.extend(label_contradictions)

    # ── 7. Structure guard veto on flattening ──
    flatten_vetoes = _check_flattening_veto(opinions, merged_targets)
    vetoes.extend(flatten_vetoes)

    # ── 8. problems: union ──
    merged_problems = _merge_problems_union(opinions, raw_analysis)

    # ── 9. confidence: weighted average ──
    merged_confidence = _merge_numeric_simple(
        [op["formplan"].get("confidence", {}) for op in opinions],
        [op["weight"] for op in opinions],
    )

    # ── 10. Contradiction detection ──
    numeric_contradictions = _detect_numeric_contradictions(opinions)
    contradictions.extend(numeric_contradictions)

    # Convert contradictions to unresolved tensions for the formplan
    unresolved_tensions = sorted(contradictions, key=lambda c: c.get("severity", 0), reverse=True)

    # Build formplan
    formplan = {
        "schema_version": "dynamic_mastering_formplan_v2",
        "track_identity": macro_winner["formplan"].get(
            "track_identity", raw_analysis.get("track_identity", {})
        ),
        "whole_track_metrics": whole_metrics,
        "whole_track_targets": merged_targets,
        "whole_track_deltas": merged_deltas,
        "macro_form": merged_macro,
        "transition_logic": merged_transitions,
        "global_mastering_strategy": merged_strategy,
        "problems": merged_problems,
        "unresolved_tensions": unresolved_tensions,
        "confidence": merged_confidence,
    }

    arbiter_report = {
        "merge_log": merge_log,
        "contradictions": unresolved_tensions,
        "vetoes_applied": vetoes,
        "field_winners": field_winners,
        "total_opinions": len(opinions),
        "agents": [
            {"key": op["agent_key"], "vendor": op["vendor"], "model": op["model"]}
            for op in opinions
        ],
    }

    return {
        "formplan": formplan,
        "arbiter_report": arbiter_report,
    }


# ══════════════════════════════════════════
# Internal: field winner selection
# ══════════════════════════════════════════
def _field_winner(opinions: list[dict], field_name: str) -> dict:
    """Return the opinion with the highest field-specific weight."""
    return max(opinions, key=lambda op: op.get("field_weights", {}).get(field_name, 0))


def _deep_copy_json(obj: Any) -> Any:
    """Deep copy via JSON serialization (safe for JSON-compatible dicts)."""
    return json.loads(json.dumps(obj))


# ══════════════════════════════════════════
# Internal: numeric merge
# ══════════════════════════════════════════
def _merge_numeric_field(
    opinions: list[dict],
    formplan_key: str,
    weight_key: str,
) -> tuple[dict, list[dict]]:
    """Merge a numeric dict field using field-specific weighted median.

    Returns (merged_dict, merge_log_entries).
    """
    dicts = [op["formplan"].get(formplan_key, {}) for op in opinions]
    weights = [op.get("field_weights", {}).get(weight_key, op["weight"]) for op in opinions]

    all_keys: set[str] = set()
    for d in dicts:
        all_keys.update(d.keys())

    merged: dict[str, Any] = {}
    log: list[dict] = []

    for key in sorted(all_keys):
        values = []
        ws = []
        for d, w in zip(dicts, weights):
            if key in d and d[key] is not None:
                values.append(d[key])
                ws.append(w)

        if not values:
            continue

        if all(isinstance(v, (int, float)) for v in values):
            result = _weighted_median(values, ws)
            merged[key] = result
            if len(values) > 1:
                spread = max(values) - min(values)
                if spread > 0.5:
                    log.append({
                        "field": f"{formplan_key}.{key}",
                        "rule": "weighted_median",
                        "values": values,
                        "weights": [round(w, 2) for w in ws],
                        "result": result,
                        "spread": round(spread, 4),
                    })
        elif all(isinstance(v, str) for v in values):
            # Majority vote (2/3)
            result = _majority_vote_str(values, ws)
            merged[key] = result
        elif all(isinstance(v, bool) for v in values):
            true_w = sum(w for v, w in zip(values, ws) if v)
            merged[key] = true_w > sum(ws) / 2
        elif all(isinstance(v, list) for v in values):
            flat = []
            seen: set[str] = set()
            for v_list in values:
                for item in v_list:
                    s = str(item)
                    if s not in seen:
                        seen.add(s)
                        flat.append(item)
            merged[key] = flat
        else:
            merged[key] = values[0]

    return merged, log


def _merge_numeric_simple(
    dicts: list[dict], weights: list[float],
) -> dict:
    """Simple weighted average for confidence-like fields."""
    all_keys: set[str] = set()
    for d in dicts:
        all_keys.update(d.keys())

    merged: dict[str, Any] = {}
    for key in all_keys:
        values = []
        ws = []
        for d, w in zip(dicts, weights):
            if key in d and isinstance(d[key], (int, float)):
                values.append(d[key])
                ws.append(w)
        if values:
            w_total = sum(ws) + 1e-10
            merged[key] = round(sum(v * w for v, w in zip(values, ws)) / w_total, 4)

    return merged


def _weighted_median(values: list[float], weights: list[float]) -> float:
    """Compute weighted median."""
    if len(values) == 1:
        return round(values[0], 4)

    pairs = sorted(zip(values, weights), key=lambda x: x[0])
    total = sum(w for _, w in pairs)
    cumulative = 0.0
    for val, w in pairs:
        cumulative += w
        if cumulative >= total / 2:
            return round(val, 4)

    return round(pairs[-1][0], 4)


def _majority_vote_str(values: list[str], weights: list[float]) -> str:
    """2/3 weighted majority for string labels. Fallback to highest weight."""
    vote_map: dict[str, float] = {}
    for v, w in zip(values, weights):
        vote_map[v] = vote_map.get(v, 0) + w

    total = sum(weights)
    for label, w in sorted(vote_map.items(), key=lambda x: -x[1]):
        if w >= total * 2 / 3:
            return label

    # No 2/3 majority — highest weight wins
    best_idx = weights.index(max(weights))
    return values[best_idx]


# ══════════════════════════════════════════
# Internal: section merge
# ══════════════════════════════════════════
def _merge_sections(
    opinions: list[dict],
    base_sections: list[dict],
    merge_log: list[dict],
) -> list[dict]:
    """Merge section-level targets across opinions."""
    section_map: dict[str, list[tuple[dict, float]]] = {}

    for op in opinions:
        weight = op.get("field_weights", {}).get("section_targets", op["weight"])
        macro = op["formplan"].get("macro_form", {})
        for sec in macro.get("sections", []):
            sid = sec.get("section_id", "")
            if sid not in section_map:
                section_map[sid] = []
            section_map[sid].append((sec.get("section_targets", {}), weight))

    for sec in base_sections:
        sid = sec.get("section_id", "")
        if sid in section_map:
            targets_list = [t for t, _ in section_map[sid]]
            weights_list = [w for _, w in section_map[sid]]
            merged, _ = _merge_numeric_field_raw(targets_list, weights_list)
            sec["section_targets"] = merged

    return base_sections


def _merge_numeric_field_raw(
    dicts: list[dict], weights: list[float],
) -> tuple[dict, list]:
    """Raw numeric merge (no formplan_key indirection)."""
    all_keys: set[str] = set()
    for d in dicts:
        all_keys.update(d.keys())

    merged: dict[str, Any] = {}
    for key in sorted(all_keys):
        values = []
        ws = []
        for d, w in zip(dicts, weights):
            if key in d and d[key] is not None and isinstance(d[key], (int, float)):
                values.append(d[key])
                ws.append(w)
        if values:
            merged[key] = _weighted_median(values, ws)

    return merged, []


# ══════════════════════════════════════════
# Internal: do_not_damage union
# ══════════════════════════════════════════
def _collect_do_not_damage(opinions: list[dict]) -> set[str]:
    """Union of all do_not_damage items across all agents and sections."""
    all_dnd: set[str] = set()
    for op in opinions:
        macro = op["formplan"].get("macro_form", {})
        for sec in macro.get("sections", []):
            for item in sec.get("do_not_damage", []):
                if isinstance(item, str):
                    all_dnd.add(item)
        # Also check global do_not_damage
        strat = op["formplan"].get("global_mastering_strategy", {})
        for item in strat.get("do_not_damage", []):
            if isinstance(item, str):
                all_dnd.add(item)
    return all_dnd


# ══════════════════════════════════════════
# Internal: failure conditions + veto
# ══════════════════════════════════════════
def _merge_failure_conditions(opinions: list[dict]) -> tuple[dict, list[dict]]:
    """Merge global_mastering_strategy with failure_conditions union.

    Returns (merged_strategy, vetoes_applied).
    """
    fc_winner = _field_winner(opinions, "failure_conditions")
    base_strategy = _deep_copy_json(
        fc_winner["formplan"].get("global_mastering_strategy", {})
    )

    # Union all failure conditions
    all_fc: list = []
    seen: set[str] = set()
    for op in opinions:
        strat = op["formplan"].get("global_mastering_strategy", {})
        for fc in strat.get("failure_conditions", []):
            fc_str = fc if isinstance(fc, str) else json.dumps(fc, sort_keys=True)
            if fc_str not in seen:
                seen.add(fc_str)
                all_fc.append(fc)

    base_strategy["failure_conditions"] = all_fc

    # Structure guard veto
    vetoes = []
    for op in opinions:
        if op["agent_key"] == "logica":
            strat = op["formplan"].get("global_mastering_strategy", {})
            for fc in strat.get("failure_conditions", []):
                fc_str = fc if isinstance(fc, str) else json.dumps(fc)
                if "flatten" in fc_str.lower() or "contrast" in fc_str.lower():
                    vetoes.append({
                        "source": f"{op['agent_key']}/{op['vendor']}",
                        "type": "structure_guard_veto",
                        "condition": fc_str,
                        "action": "enforced_as_hard_constraint",
                    })

    return base_strategy, vetoes


def _check_flattening_veto(opinions: list[dict], merged_targets: dict) -> list[dict]:
    """Check if structure_guard raises flattening concerns against merged targets."""
    vetoes = []
    for op in opinions:
        if op["agent_key"] != "logica":
            continue

        # Check if structure_guard's section contrast target is being violated
        guard_targets = op["formplan"].get("whole_track_targets", {})
        guard_lra = guard_targets.get("target_lra_lu")
        merged_lra = merged_targets.get("target_lra_lu")

        if guard_lra and merged_lra and merged_lra < guard_lra * 0.8:
            # Merged LRA is significantly lower than structure_guard wants
            vetoes.append({
                "source": f"{op['agent_key']}/{op['vendor']}",
                "type": "lra_flattening_veto",
                "guard_target": guard_lra,
                "merged_target": merged_lra,
                "action": "adjusted_to_guard_minimum",
            })
            # Apply veto: raise merged LRA to guard's minimum
            merged_targets["target_lra_lu"] = round(guard_lra * 0.9, 2)

    return vetoes


# ══════════════════════════════════════════
# Internal: label majority + contradiction detection
# ══════════════════════════════════════════
def _check_label_majority(opinions: list[dict]) -> list[dict]:
    """Check if section labels have 2/3 majority across agents."""
    contradictions = []

    # Collect section labels per section_id
    label_map: dict[str, dict[str, list[str]]] = {}
    for op in opinions:
        macro = op["formplan"].get("macro_form", {})
        for sec in macro.get("sections", []):
            sid = sec.get("section_id", "")
            label = sec.get("heuristic_label") or sec.get("structural_role", "")
            if sid and label:
                if sid not in label_map:
                    label_map[sid] = {}
                agent_id = f"{op['agent_key']}/{op['vendor']}"
                label_map[sid][agent_id] = label

    for sid, labels in label_map.items():
        unique_labels = set(labels.values())
        if len(unique_labels) > 1:
            # No unanimous agreement
            label_counts: dict[str, int] = {}
            for lbl in labels.values():
                label_counts[lbl] = label_counts.get(lbl, 0) + 1

            majority = max(label_counts.values())
            if majority < 2:
                # No 2/3 majority — contradiction
                contradictions.append({
                    "field": f"macro_form.sections.{sid}.label",
                    "type": "label_disagreement",
                    "positions": labels,
                    "severity": 0.5 if majority == 1 else 0.3,
                })

    return contradictions


def _detect_numeric_contradictions(opinions: list[dict]) -> list[dict]:
    """Detect significant numeric disagreements between agents."""
    contradictions = []

    all_target_keys: set[str] = set()
    for op in opinions:
        all_target_keys.update(op["formplan"].get("whole_track_targets", {}).keys())

    for key in sorted(all_target_keys):
        values = {}
        for op in opinions:
            v = op["formplan"].get("whole_track_targets", {}).get(key)
            if v is not None and isinstance(v, (int, float)):
                values[f"{op['agent_key']}/{op['vendor']}"] = v

        if len(values) < 2:
            continue

        nums = list(values.values())
        spread = max(nums) - min(nums)

        # Threshold: significant if spread > 2.0 or relative spread > 20%
        mean_abs = sum(abs(v) for v in nums) / len(nums) + 0.01
        relative_spread = spread / mean_abs

        if spread > 2.0 or relative_spread > 0.2:
            contradictions.append({
                "field": f"whole_track_targets.{key}",
                "type": "numeric_contradiction",
                "positions": values,
                "spread": round(spread, 4),
                "relative_spread": round(relative_spread, 4),
                "severity": round(min(spread / 5.0, 1.0), 3),
            })

    return contradictions


# ══════════════════════════════════════════
# Internal: problems union
# ══════════════════════════════════════════
def _merge_problems_union(opinions: list[dict], raw_analysis: dict) -> list[dict]:
    """Union of all problems, deduplicated by code+section_id."""
    all_problems = []
    seen: set[tuple] = set()

    for p in raw_analysis.get("detected_problems", []):
        key = (p.get("code"), p.get("section_id"))
        if key not in seen:
            seen.add(key)
            all_problems.append(p)

    for op in opinions:
        for p in op["formplan"].get("problems", []):
            key = (p.get("code"), p.get("section_id"))
            if key not in seen:
                seen.add(key)
                all_problems.append(p)

    return all_problems

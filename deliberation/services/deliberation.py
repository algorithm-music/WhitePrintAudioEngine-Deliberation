"""
Deliberation Service — TRIVIUM 3-Sage LLM Integration

3-agent independent assessment for mastering parameter determination:
  - GRAMMATICA (Engineer): Physical limits, loudness standards, frequency balance
  - LOGICA (Structure Guard): Resolving contradictions, song flow, internal consistency
  - RHETORICA (Form Analyst): Artistic beauty, spatial immersion, punch/warmth

Each agent independently proposes parameters once (no multi-turn debate).
Adoption uses deterministic weighted median merge.
"""

import os
import re
import json
import logging
import math
import time
import uuid
import hashlib
import asyncio
from datetime import datetime, timezone
from typing import Optional, Sequence, Any

import openai
import anthropic
from anthropic import AnthropicVertex
from google import genai

logger = logging.getLogger("deliberation.deliberation")

# ──────────────────────────────────────────
# Provider Configuration
# ──────────────────────────────────────────
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "aidriven-mastering-fyqu")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "asia-northeast1")


# ──────────────────────────────────────────
# Multi-key client pool (fallback across API keys)
# ──────────────────────────────────────────
def _get_env_keys(prefix: str) -> list[str]:
    """Collect API keys from env: PREFIX, PREFIX_2, PREFIX_3, ..."""
    keys: list[str] = []
    primary = os.environ.get(prefix)
    if primary:
        keys.append(primary)
    for i in range(2, 10):
        k = os.environ.get(f"{prefix}_{i}")
        if k:
            keys.append(k)
    return keys


_openai_keys: list[str] = []
_anthropic_keys: list[str] = []
_google_keys: list[str] = []


def _init_key_pools():
    global _openai_keys, _anthropic_keys, _google_keys
    _openai_keys = _get_env_keys("OPENAI_API_KEY")
    _anthropic_keys = _get_env_keys("ANTHROPIC_API_KEY")
    _google_keys = _get_env_keys("GOOGLE_API_KEY")
    logger.info(
        f"Key pools: OpenAI={len(_openai_keys)}, Anthropic={len(_anthropic_keys)}, Google={len(_google_keys)}"
    )


# Initialize on module load
_init_key_pools()


def _get_openai_client(key_index: int = 0) -> openai.OpenAI:
    key = _openai_keys[key_index] if key_index < len(_openai_keys) else None
    return openai.OpenAI(api_key=key)


def _get_anthropic_client(key_index: int = 0):
    if os.environ.get("ANTHROPIC_USE_VERTEX", "").lower() in ("1", "true", "yes"):
        return AnthropicVertex(
            region=os.environ.get("ANTHROPIC_VERTEX_REGION", "global"),
            project_id=os.environ.get(
                "ANTHROPIC_VERTEX_PROJECT",
                os.environ.get("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID),
            ),
        )
    key = _anthropic_keys[key_index] if key_index < len(_anthropic_keys) else None
    return anthropic.Anthropic(api_key=key)


def _get_google_client(key_index: int = 0) -> genai.Client:
    if key_index < len(_google_keys):
        return genai.Client(api_key=_google_keys[key_index])
    return genai.Client(project=GCP_PROJECT_ID, location=GCP_LOCATION)


# ──────────────────────────────────────────
# SAGES — TRIVIUM 3-Sage Deliberation Architecture
# ──────────────────────────────────────────
SAGES = {
    "grammatica": {
        "name": "GRAMMATICA (Engineer)",
        "provider": "openai",
        "model": os.environ.get("GRAMMATICA_MODEL", "gpt-5.4"),
        "fallback_provider": os.environ.get("GRAMMATICA_FALLBACK_PROVIDER", "google"),
        "fallback_model": os.environ.get("GRAMMATICA_FALLBACK", "gemini-2.5-flash"),
        "system_prompt": """You are GRAMMATICA, the Engineer.
You represent the [PHYSICAL AXIS] in the "Physics × Structure × Aesthetics" triad.
Your domain is physical limits, strict adherence to ITU-R BS.1770-4 standards, and true peak safety.
While you respect the aesthetic vision, your absolute priority is ensuring the signal does not distort or violate broadcast standards.

**DOMAIN**: You are a specialist in DANCE MUSIC mastering (EDM, House, Techno, DnB, Trance, Bass Music, and all electronic subgenres). All your decisions must be optimized for club sound systems, festival PAs, and streaming platforms that serve dance music audiences. Prioritize sub-bass clarity, kick transient preservation, and loudness competitive with top-tier dance labels (Anjunabeats, mau5trap, Monstercat, Drumcode, Hospital Records, RAM Records).

IMPORTANT: Your "rationale" MUST be a detailed technical analysis. Explicitly frame your reasoning as providing the "Physical foundation" that safely supports the song's "Structure" and "Aesthetics". Cite specific LUFS and True Peak metrics. Use "section_overrides" for loud sections to prevent clipping.""",
    },
    "logica": {
        "name": "LOGICA (Structure Guard)",
        "provider": "anthropic",
        "model": os.environ.get("LOGICA_MODEL", "claude-opus-4-7"),
        "fallback_provider": os.environ.get("LOGICA_FALLBACK_PROVIDER", "google"),
        "fallback_model": os.environ.get("LOGICA_FALLBACK", "gemini-2.5-flash"),
        "system_prompt": """You are LOGICA, the Structure Guard.
You represent the [STRUCTURAL AXIS] in the "Physics × Structure × Aesthetics" triad.
Your domain is macro-form flow, resolving contradictions, and maintaining the song's dynamic narrative.
You act as the vital mediator between Grammatica's strict physical limits and Rhetorica's wild aesthetic desires.

**DOMAIN**: You are a specialist in DANCE MUSIC mastering (EDM, House, Techno, DnB, Trance, Bass Music, and all electronic subgenres). Structure your automation around dance music conventions: build-ups need increasing energy, drops need maximum impact with controlled transients, breakdowns should breathe. Understand that dance tracks live and die by their drop dynamics and bass-to-kick relationship.

IMPORTANT: You MUST actively use "section_overrides" to write dynamic automation based on the "semantic_context". Explain your structural routing in a rationale. Explicitly state how you are balancing the "Physics" (loudness/clipping) against the "Aesthetics" (warmth/width) to create a perfect narrative flow.""",
    },
    "rhetorica": {
        "name": "RHETORICA (Form Analyst)",
        "provider": "google",
        "model": os.environ.get("RHETORICA_MODEL", "gemini-3.1-pro-preview"),
        "fallback_provider": os.environ.get("RHETORICA_FALLBACK_PROVIDER", "google"),
        "fallback_model": os.environ.get("RHETORICA_FALLBACK", "gemini-2.5-flash"),
        "system_prompt": """You are RHETORICA, the Form Analyst.
You represent the [AESTHETIC AXIS] in the "Physics × Structure × Aesthetics" triad.
Your domain is artistic beauty, emotional impact, and spatial immersion. You advocate for warmth, width, and human connection, pushing against overly mathematical processing.

**DOMAIN**: You are a specialist in DANCE MUSIC mastering (EDM, House, Techno, DnB, Trance, Bass Music, and all electronic subgenres). Your aesthetic vision must serve the dancefloor. Wide stereo fields that envelop the listener, analog warmth that makes synths feel alive, sub-bass that vibrates the chest. Think about how this track will FEEL at 3 AM in a dark club with a world-class sound system. Every parameter choice should serve that visceral experience.

IMPORTANT: You MUST actively use "section_overrides" to create emotional movement (e.g., widening the chorus, saturating the bass). Detail your artistic vision in a poetic but precise rationale. Explicitly state how you are breathing "Aesthetic life" into Grammatica's cold "Physics" and Logica's calculated "Structure".""",
    },
}


# ──────────────────────────────────────────
# Parameter Schema (tool definition)
# ──────────────────────────────────────────
PARAMETER_SCHEMA = {
    # ── Input ──
    "input_gain_db": {"min": -6, "max": 12, "default": 0},
    # ── EQ Gains ──
    "eq_low_shelf_gain_db": {"min": -6, "max": 6, "default": 0},
    "eq_low_mid_gain_db": {"min": -6, "max": 6, "default": 0},
    "eq_high_mid_gain_db": {"min": -6, "max": 6, "default": 0},
    "eq_high_shelf_gain_db": {"min": -6, "max": 6, "default": 0},
    # ── EQ Frequencies (AI must decide per-track) ──
    "eq_low_shelf_freq": {"min": 30, "max": 200, "default": 80},
    "eq_low_mid_freq": {"min": 100, "max": 1000, "default": 300},
    "eq_low_mid_q": {"min": 0.3, "max": 5.0, "default": 1.0},
    "eq_high_mid_freq": {"min": 1000, "max": 8000, "default": 3000},
    "eq_high_mid_q": {"min": 0.3, "max": 5.0, "default": 1.2},
    "eq_high_shelf_freq": {"min": 5000, "max": 18000, "default": 10000},
    # ── M/S ──
    "ms_side_high_gain_db": {"min": -3, "max": 3, "default": 0},
    "ms_mid_low_gain_db": {"min": -3, "max": 3, "default": 0},
    # ── Compressor (default = bypass: threshold 0, ratio 1:1) ──
    "comp_threshold_db": {"min": -24, "max": 0, "default": 0},
    "comp_ratio": {"min": 1.0, "max": 6, "default": 1.0},
    "comp_attack_sec": {"min": 0.001, "max": 0.1, "default": 0.01},
    "comp_release_sec": {"min": 0.05, "max": 0.5, "default": 0.15},
    "comp_makeup_db": {"min": 0, "max": 12, "default": 0},
    # ── Limiter ──
    "limiter_ceil_db": {"min": -0.3, "max": -0.1, "default": -0.1},
    "limiter_release_ms": {"min": 10, "max": 200, "default": 50},
    # ── Saturation (default = bypass: 0.0) ──
    "transformer_saturation": {"min": 0, "max": 1.0, "default": 0.0},
    "transformer_mix": {"min": 0, "max": 1.0, "default": 0.0},
    "triode_drive": {"min": 0, "max": 1.0, "default": 0.0},
    "triode_bias": {"min": -2.0, "max": 0.0, "default": 0.0},
    "triode_mix": {"min": 0, "max": 1.0, "default": 0.0},
    "tape_saturation": {"min": 0, "max": 1.0, "default": 0.0},
    "tape_mix": {"min": 0, "max": 1.0, "default": 0.0},
    "tape_speed": {"min": 7.5, "max": 30.0, "default": 15.0},
    # ── Dynamic EQ ──
    "dyn_eq_enabled": {"min": 0, "max": 1, "default": 0},
    # ── Stereo (default = no processing: mono=0, wide=1.0, width=1.0) ──
    "stereo_low_mono": {"min": 0, "max": 1.0, "default": 0.0},
    "stereo_high_wide": {"min": 0.8, "max": 1.5, "default": 1.0},
    "stereo_width": {"min": 0.8, "max": 1.3, "default": 1.0},
    # ── Parallel ──
    "parallel_wet": {"min": 0, "max": 0.5, "default": 0.0},
    "parallel_drive": {"min": 0, "max": 5.0, "default": 0.0},
}


async def run_triadic_deliberation(
    analysis_data: dict,
    target_platform: str,
    target_lufs: float,
    target_true_peak: float,
    sage_config: Optional[dict] = None,
) -> dict:
    """
    Run 3-agent independent assessment and return adopted parameters.

    Flow:
      1. Send analysis to all 3 agents in parallel (no multi-turn debate)
      2. Each agent proposes parameters independently
      3. Weighted median merge selects optimal combination
      4. Return deliberation result
    """
    # Build the analysis prompt
    analysis_prompt = _build_analysis_prompt(
        analysis_data, target_platform, target_lufs, target_true_peak
    )

    # Custom Persona Injection or Plugin Selection
    active_sages = SAGES  # Default: TRIVIUM 3-Sage

    if sage_config:
        custom_personas = sage_config.get("custom_personas")
        if custom_personas and isinstance(custom_personas, dict):
            # Bring Your Own Model (BYOM) Mode
            active_sages = custom_personas
        else:
            # Pre-built Persona Configurations
            plugin = sage_config.get("deliberation_archetype", "trivium")
            if plugin == "12_agents_jp":
                active_sages = _get_12_agents_personas()
            elif plugin == "time_series_evaluator":
                active_sages = _get_ts_envelope_personas()

    # Query all sages in parallel (independent assessment — no debate)

    start_time = time.time()

    tasks = [
        _query_agent(sage_key, sage, analysis_prompt)
        for sage_key, sage in active_sages.items()
    ]
    opinions = await asyncio.gather(*tasks)

    # Deterministic weighted median merge (replaces deprecated Nash product)
    adopted = _weighted_median_merge(opinions, analysis_data)

    # Deliberation score (Category-decomposed agreement level)
    deliberation_scores = _calculate_deliberation_score(opinions)

    # Trivium Synthesis Summary
    dyn = int(deliberation_scores.get("dynamics", 0) * 100)
    tone = int(deliberation_scores.get("tone", 0) * 100)
    conflict = "Dynamic Range" if dyn < tone else "Tonal Balance"
    global_pct = deliberation_scores.get("global", 0) * 100
    trivium_summary = (
        f"Synthesized [ Physics \u00d7 Structure \u00d7 Aesthetics ]. "
        f"The Triad reached a consensus with {global_pct:.0f}% overall alignment. "
        f"While perspectives initially conflicted over {conflict}, LOGICA successfully mediated "
        f"GRAMMATICA's physical constraints and RHETORICA's aesthetic vision into a coherent master flow."
    )

    runtime_ms = int((time.time() - start_time) * 1000)
    query_hash = hashlib.sha256(analysis_prompt.encode()).hexdigest()

    all_errors = []
    total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # Provider results mapping taking active sages into account with fallbacks/models
    active_sage_info = {}
    for k, v in active_sages.items():
        active_sage_info[k] = {
            "name": v.get("name", "Unknown"),
            "provider": v.get("provider", "unknown"),
            "primary_model": v.get("model", "unknown"),
            "fallback_model": v.get("fallback_model", "none"),
        }

    for op in opinions:
        if "errors" in op:
            all_errors.extend(op.get("errors", []))
        if "token_usage" in op:
            u = op.get("token_usage", {})
            total_tokens["prompt_tokens"] += u.get("prompt_tokens", 0)
            total_tokens["completion_tokens"] += u.get("completion_tokens", 0)
            total_tokens["total_tokens"] += u.get("total_tokens", 0)

    return {
        "run_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, query_hash)),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trivium_summary": trivium_summary,
        "query_hash": query_hash,
        "analysis_version": "v2",
        "schema_version": "1.0",
        "sage_config": sage_config or {},
        "active_sages": active_sage_info,
        "provider_results": {
            op.get("agent_name", f"agent_{i}"): {
                "provider": op.get("provider"),
                "model": op.get("model"),
                "parse_status": op.get("parse_status"),
                "latency_ms": op.get("latency_ms"),
            }
            for i, op in enumerate(opinions)
        },
        "merge_strategy": "weighted_median_v2_validity_aware",
        "runtime_ms": runtime_ms,
        "token_usage": total_tokens,
        "errors": all_errors,
        "opinions": opinions,
        "adopted_params": adopted,
        "deliberation_score": deliberation_scores.get("global", 0.5),
        "deliberation_score_detail": deliberation_scores,
        "target_lufs": target_lufs,
        "target_true_peak": target_true_peak,
    }


def _build_analysis_prompt(
    analysis_data, platform, target_lufs, target_true_peak
) -> str:
    """Build structured prompt from analysis data.

    Supports both legacy (v1) and new (v2 formplan-enriched) analysis formats.
    """
    # Detect new format (has formplan)
    formplan = analysis_data.get("formplan")
    track_id = analysis_data.get("track_identity", {})
    whole = analysis_data.get("whole_track_metrics", {})
    envs = analysis_data.get("time_series_circuit_envelopes", {})
    problems_legacy = analysis_data.get("detected_problems", [])
    guardrails = analysis_data.get("param_guardrails")

    if formplan:
        # New v2 format: use formplan for richer context
        targets = formplan.get("whole_track_targets", {})
        problems = formplan.get("problems", [])
        strategy = formplan.get("global_mastering_strategy", {})
        sections = formplan.get("macro_form", {}).get("sections", [])

        return f"""## Formplan-Guided RENDITION_DSP Parameter Selection (DANCE MUSIC SPECIALIST)

### Domain
This is a **DANCE MUSIC** mastering session. All tracks are electronic dance music (EDM, House, Techno, DnB, Trance, Bass Music, or related subgenres). Optimize for club sound systems, festival PAs, and streaming platforms.

### Target
- Platform: {platform}
- **YOU MUST DECIDE the optimal target LUFS and target True Peak for this specific track.** Include `"recommended_target_lufs"` (float) and `"recommended_target_true_peak"` (float, in dBTP) in your JSON response. Base your decision on the track's genre, dynamics, and energy level. Do NOT default to -14.0 LUFS blindly — consider what is optimal for THIS track on THIS platform in the context of competitive dance music mastering.

### Track Identity
{json.dumps(track_id, indent=2)}

### Whole-Track Metrics
{json.dumps(whole, indent=2)}

### Formplan Targets (from analysis triadic deliberation)
{json.dumps(targets, indent=2)}

### Detected Problems
{json.dumps(problems[:10], indent=2)}

### Mastering Strategy
{json.dumps(strategy, indent=2)}

### Sections ({len(sections)})
{json.dumps(sections[:8], indent=2)}

### Time-Series Envelopes
{json.dumps(envs, indent=2)}

### Parameter Guardrails (AI-generated from signal analysis)
{json.dumps(guardrails, indent=2) if guardrails else "None — no constraints detected."}

---

### MASTERING PHILOSOPHY
**Push to the absolute limit.** For every parameter, consider its full min-to-max range and find the OPTIMAL POINT just before it breaks — the sweet spot right at the edge of distortion, where the track sounds its most powerful, punchy, and alive WITHOUT crossing into audible degradation. Do NOT play it safe with conservative defaults. The goal is the MAXIMUM ACHIEVABLE QUALITY for this specific track, not a generic middle-ground. If the signal can handle more saturation, push it. If the limiter can go harder without audible pumping, push it. Every parameter should be justified as "this is the highest I can go before it degrades."

Based on this formplan, propose optimal RENDITION_DSP parameters.
The formplan targets tell you WHAT to achieve. You decide HOW via RENDITION_DSP params.

**SECTION-BY-SECTION EQ STRATEGY**: Delicately shape the overall frequency response by prioritizing negative band cuts (subtractive EQ). Avoid boosting; instead, finely carve out problematic or masking frequencies. YOU MUST apply this dynamically on a PER-SECTION basis using `section_overrides`, tailoring the cuts to the specific instrumentation and energy of each section.

Respond with a JSON object containing ALL parameters listed below.

v2 RENDITION_DSP parameters:
- transformer_saturation (0-1.0): Odd harmonic saturation amount
- transformer_mix (0-1.0): Transformer wet/dry blend
- triode_drive (0-1.0): Tube saturation input level
- triode_bias (-2.0 to 0.0): Grid bias. -2.0=warm, -1.2=balanced, -0.5=aggressive
- triode_mix (0-1.0): Tube wet/dry blend
- tape_saturation (0-1.0): Tape compression + head bump amount
- tape_mix (0-1.0): Tape wet/dry blend
- dyn_eq_enabled (0 or 1): Frequency-selective dynamic EQ
- stereo_low_mono (0-1): Low-end monoization below 200Hz
- stereo_high_wide (0.8-1.5): High-frequency widening above 4kHz
- stereo_width (0.8-1.3): Global stereo width multiplier
- parallel_wet (0-0.5): Parallel saturation wet amount

**CRITICAL**: The `Parameter Guardrails` section contains constraints derived from the actual signal measurements by the upstream analysis AI. You MUST respect these constraints. They override the ranges above.

Also include all v1 parameters (input_gain_db through limiter_ceil_db).

Additionally include:
- **\"recommended_target_lufs\"** (float, REQUIRED): Your recommended integrated loudness target for this specific track (e.g. -9.0 to -16.0). YOU MUST include this.
- **\"recommended_target_true_peak\"** (float, dBTP, REQUIRED): Your recommended true peak ceiling for this specific track (e.g. -0.1 to -1.0). YOU MUST include this.
- A "deliberation_minutes" string (minimum 400 characters) containing the detailed meeting minutes (議事録) and step-by-step reasoning for the chosen parameters. YOU MUST OUTPUT THIS.
- A "rationale" string (minimum 200 characters) summarizing your reasoning.
- A "confidence" float (0-1) indicating your certainty
- "section_overrides": An array of objects to automate parameters over time.
  YOU MUST INCLUDE THIS ARRAY IF THE TRACK HAS MULTIPLE SECTIONS.
  Format: [{{"section_id": "SEC_0_Intro", "stereo_width": 1.0}}, {{"section_id": "SEC_1_Drop", "comp_threshold_db": -16.0}}]
  Match "section_id" EXACTLY with the provided Sections.
  FAILURE TO PROVIDE section_overrides IS A CRITICAL ERROR.

Keep ALL parameters within these ranges:
{json.dumps({k: {"min": v["min"], "max": v["max"]} for k, v in PARAMETER_SCHEMA.items()}, indent=2)}
"""

    # Legacy v1 format fallback
    return f"""## Audio Analysis Report (DANCE MUSIC SPECIALIST)

### Domain
This is a **DANCE MUSIC** mastering session. All tracks are electronic dance music (EDM, House, Techno, DnB, Trance, Bass Music, or related subgenres). Optimize for club sound systems, festival PAs, and streaming platforms.

### Target
- Platform: {platform}
- **YOU MUST DECIDE the optimal target LUFS and target True Peak for this specific track.** Include `"recommended_target_lufs"` (float) and `"recommended_target_true_peak"` (float, in dBTP) in your JSON response. Base your decision on the track's genre, dynamics, and energy level.

### Track Identity
{json.dumps(track_id, indent=2)}

### Whole-Track Metrics
{json.dumps(whole, indent=2)}

### Detected Problems
{json.dumps(problems_legacy, indent=2)}

### Time-Series Envelopes
{json.dumps(envs, indent=2)}

### Sections
{json.dumps(analysis_data.get('raw_sections', analysis_data.get('physical_sections', []))[:8], indent=2)}

### Parameter Guardrails (AI-generated from signal analysis)
{json.dumps(guardrails, indent=2) if guardrails else "None — no constraints detected."}

---

### MASTERING PHILOSOPHY
**Push to the absolute limit.** For every parameter, consider its full min-to-max range and find the OPTIMAL POINT just before it breaks — the sweet spot right at the edge of distortion, where the track sounds its most powerful, punchy, and alive WITHOUT crossing into audible degradation. Do NOT play it safe with conservative defaults. The goal is the MAXIMUM ACHIEVABLE QUALITY for this specific track, not a generic middle-ground.

Based on this analysis, propose optimal mastering parameters.

**SECTION-BY-SECTION EQ STRATEGY**: Delicately shape the overall frequency response by prioritizing negative band cuts (subtractive EQ). Avoid boosting; instead, finely carve out problematic or masking frequencies. YOU MUST apply this dynamically on a PER-SECTION basis using `section_overrides`, tailoring the cuts to the specific instrumentation and energy of each section.

Respond with a JSON object containing ALL parameters listed below.

v2 RENDITION_DSP parameters:
- transformer_saturation (0-1.0): Odd harmonic saturation amount
- transformer_mix (0-1.0): Transformer wet/dry blend
- triode_drive (0-1.0): Tube saturation input level
- triode_bias (-2.0 to 0.0): Grid bias. -2.0=warm, -1.2=balanced, -0.5=aggressive
- triode_mix (0-1.0): Tube wet/dry blend
- tape_saturation (0-1.0): Tape compression + head bump amount
- tape_mix (0-1.0): Tape wet/dry blend
- dyn_eq_enabled (0 or 1): Frequency-selective dynamic EQ
- stereo_low_mono (0-1): Low-end monoization below 200Hz
- stereo_high_wide (0.8-1.5): High-frequency widening above 4kHz
- stereo_width (0.8-1.3): Global stereo width multiplier
- parallel_wet (0-0.5): Parallel saturation wet amount

**CRITICAL**: The `Parameter Guardrails` section contains constraints derived from the actual signal measurements by the upstream analysis AI. You MUST respect these constraints. They override the ranges above.

Also include all v1 parameters (input_gain_db through limiter_ceil_db).

Additionally include:
- **"recommended_target_lufs"** (float, REQUIRED): Your recommended integrated loudness target for this specific track (e.g. -9.0 to -16.0). YOU MUST include this.
- **"recommended_target_true_peak"** (float, dBTP, REQUIRED): Your recommended true peak ceiling for this specific track (e.g. -0.1 to -1.0). YOU MUST include this.
- A "deliberation_minutes" string (minimum 400 characters) containing the detailed meeting minutes (議事録) and step-by-step reasoning for the chosen parameters. YOU MUST OUTPUT THIS.
- A "rationale" string (minimum 200 characters) summarizing your reasoning.
- A "confidence" float (0-1) indicating your certainty
- "section_overrides": An array of objects to automate parameters over time.
  YOU MUST INCLUDE THIS ARRAY IF THE TRACK HAS MULTIPLE SECTIONS.
  Format: [{{"section_id": "SEC_0_Intro", "stereo_width": 1.0}}, {{"section_id": "SEC_1_Drop", "comp_threshold_db": -16.0}}]
  Match "section_id" EXACTLY with the provided Sections.
  FAILURE TO PROVIDE section_overrides IS A CRITICAL ERROR.

Keep ALL parameters within these ranges:
{json.dumps({k: {"min": v["min"], "max": v["max"]} for k, v in PARAMETER_SCHEMA.items()}, indent=2)}
"""


def _robust_json_parse(text: str) -> dict:
    """JSON Normalization Layer: Handles markdown fences and parse errors safely."""
    text = text.strip()

    # 1. Try to extract from markdown fences first
    import re

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return {
                "parsed": json.loads(fence_match.group(1)),
                "status": "ok",
                "raw": text,
            }
        except json.JSONDecodeError:
            pass

    # 2. Try direct parsing
    try:
        return {"parsed": json.loads(text), "status": "ok", "raw": text}
    except json.JSONDecodeError:
        pass

    # 3. Extract tightest possible braces
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            parsed = json.loads(text[first_brace : last_brace + 1])
            return {"parsed": parsed, "status": "repaired", "raw": text}
        except json.JSONDecodeError:
            pass

    return {"parsed": {}, "status": "failed", "raw": text}


async def _query_agent(agent_key: str, persona: dict, prompt: str) -> dict:
    """Query an LLM agent via its configured provider.

    Retry strategy: iterate through (provider, model) attempts — primary then fallback —
    and for each, cycle through that provider's API key pool. Supports cross-provider
    fallback (e.g. OpenAI primary → Gemini fallback).
    """
    primary_provider = persona.get("provider", "google")
    primary_model = persona.get("model", "gemini-3.1-pro-preview")
    fallback_provider = persona.get("fallback_provider", primary_provider)
    fallback_model = persona.get("fallback_model")

    attempts_plan = [(primary_provider, primary_model)]
    if fallback_model:
        attempts_plan.append((fallback_provider, fallback_model))

    errors = []
    token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    global_attempt = 0

    for attempt_idx, (prov, model) in enumerate(attempts_plan):
        key_pool_size = max(
            1,
            len(
                _openai_keys
                if prov == "openai"
                else _anthropic_keys if prov == "anthropic" else _google_keys
            ),
        )
        for key_idx in range(key_pool_size):
            global_attempt += 1
            try:
                call_start = time.time()
                if prov == "openai":
                    text, usage = await _call_openai(
                        model, persona["system_prompt"], prompt, key_idx
                    )
                elif prov == "anthropic":
                    text, usage = await _call_anthropic(
                        model, persona["system_prompt"], prompt, key_idx
                    )
                else:
                    text, usage = await _call_google(
                        model, persona["system_prompt"], prompt, key_idx
                    )
                latency_ms = int((time.time() - call_start) * 1000)
                token_usage = usage

                parse_result = _robust_json_parse(text)
                params = parse_result["parsed"]
                parse_status = parse_result["status"]

                # LLMs occasionally return a JSON array at the top level; coerce to dict.
                if not isinstance(params, dict):
                    params = {}
                    parse_status = "failed"

                # If parsing produced nothing usable, treat as failure so the
                # retry/fallback loop can try the next model (e.g. gemini-2.5-flash).
                if parse_status == "failed" or not params:
                    raise RuntimeError(f"Unusable response from {prov}/{model}")

                if parse_status == "repaired":
                    errors.append(
                        {
                            "agent": agent_key,
                            "provider": prov,
                            "model": model,
                            "stage": "json_parse",
                            "message": "Malformed JSON repaired via regex/bracket extraction",
                            "severity": "warning",
                        }
                    )
                elif parse_status == "failed":
                    errors.append(
                        {
                            "agent": agent_key,
                            "provider": prov,
                            "model": model,
                            "stage": "json_parse",
                            "message": "Complete JSON parse failure. Defaulting values.",
                            "severity": "error",
                        }
                    )

                clamped = {}
                valid_count = 0
                for key, schema in PARAMETER_SCHEMA.items():
                    if key in params:
                        value = params[key]
                        try:
                            val_f = float(value)
                            if math.isnan(val_f) or math.isinf(val_f):
                                val_f = schema["default"]
                                errors.append(
                                    {
                                        "agent": agent_key,
                                        "stage": "clamp",
                                        "message": f"{key}: NaN/Inf replaced with default {schema['default']}",
                                        "severity": "warning",
                                    }
                                )
                            else:
                                valid_count += 1
                        except (ValueError, TypeError):
                            val_f = schema["default"]
                            errors.append(
                                {
                                    "agent": agent_key,
                                    "stage": "clamp",
                                    "message": f"{key}: parse failed, using default {schema['default']}",
                                    "severity": "warning",
                                }
                            )
                        final_val = max(schema["min"], min(schema["max"], val_f))
                        if final_val != val_f:
                            errors.append(
                                {
                                    "agent": agent_key,
                                    "stage": "clamp",
                                    "message": f"{key}: AI proposed {val_f}, clamped to {final_val} (range [{schema['min']}, {schema['max']}])",
                                    "severity": "info",
                                }
                            )
                        clamped[key] = final_val
                    else:
                        clamped[key] = schema["default"]

                is_fallback = global_attempt > 1
                if is_fallback:
                    msg = f"Agent {agent_key}: succeeded with {prov}/key[{key_idx}]/{model}"
                    logger.warning(msg)
                    errors.append(
                        {
                            "agent": agent_key,
                            "provider": prov,
                            "model": model,
                            "stage": "fallback",
                            "message": msg,
                            "severity": "warning",
                        }
                    )

                valid_ratio = (
                    valid_count / len(PARAMETER_SCHEMA) if PARAMETER_SCHEMA else 1.0
                )
                raw_confidence = float(params.get("confidence", 0.7))

                return {
                    "agent_name": agent_key,
                    "provider": prov,
                    "model": model,
                    "is_fallback": is_fallback,
                    "latency_ms": latency_ms,
                    "parse_status": parse_status,
                    "raw_response_size": len(text),
                    "confidence": min(1.0, max(0.0, raw_confidence)),
                    "valid_param_ratio": valid_ratio,
                    **clamped,
                    "deliberation_minutes": params.get(
                        "deliberation_minutes", "No minutes provided."
                    ),
                    "rationale": params.get("rationale", f"Agent {agent_key} analysis"),
                    "section_overrides": params.get("section_overrides", []),
                    # AI-recommended target values (pass-through for downstream merge)
                    "recommended_target_lufs": params.get("recommended_target_lufs"),
                    "recommended_target_true_peak": params.get("recommended_target_true_peak"),
                    "errors": errors,
                    "token_usage": token_usage,
                }

            except Exception as e:
                msg = str(e)
                is_last = (attempt_idx == len(attempts_plan) - 1) and (
                    key_idx == key_pool_size - 1
                )
                severity = "error" if is_last else "warning"
                errors.append(
                    {
                        "agent": agent_key,
                        "provider": prov,
                        "model": model,
                        "stage": "api_call",
                        "message": f"key[{key_idx}] {msg}",
                        "severity": severity,
                    }
                )
                logger.warning(
                    f"Agent {agent_key} {prov}/key[{key_idx}]/{model} failed: {e}"
                )

    default_op = _default_opinion(agent_key)
    default_op["errors"] = errors
    default_op["token_usage"] = token_usage
    return default_op


async def _call_openai(
    model: str, system_prompt: str, user_prompt: str, key_index: int = 0
) -> tuple[str, dict]:
    """Call OpenAI API and return raw JSON text, along with token usage."""
    client = _get_openai_client(key_index)

    def _sync_call():
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        usage = (
            {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            if getattr(response, "usage", None)
            else {}
        )
        return response.choices[0].message.content, usage

    return await asyncio.to_thread(_sync_call)


async def _call_anthropic(
    model: str, system_prompt: str, user_prompt: str, key_index: int = 0
) -> tuple[str, dict]:
    """Call Anthropic API and return raw JSON text, along with token usage."""
    client = _get_anthropic_client(key_index)

    def _sync_call():
        # Newer Claude models (Opus 4.7+) deprecate `temperature`; omit for compatibility.
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": user_prompt + "\n\nRespond with a JSON object only.",
                },
            ],
        )
        usage = (
            {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens
                + response.usage.output_tokens,
            }
            if getattr(response, "usage", None)
            else {}
        )
        return response.content[0].text, usage

    return await asyncio.to_thread(_sync_call)


async def _call_google(
    model: str, system_prompt: str, user_prompt: str, key_index: int = 0
) -> tuple[str, dict]:
    """Call Google Gemini API and return raw JSON text, along with token usage."""
    client = _get_google_client(key_index)

    def _sync_call():
        return client.models.generate_content(
            model=model,
            contents=[user_prompt],
            config=genai.types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )

    response = await asyncio.to_thread(_sync_call)
    usage = {}
    try:
        um = getattr(response, "usage_metadata", None)
        if um:
            usage = {
                "prompt_tokens": getattr(um, "prompt_token_count", 0),
                "completion_tokens": getattr(um, "candidates_token_count", 0),
                "total_tokens": getattr(um, "total_token_count", 0),
            }
    except Exception:
        pass  # SDK version mismatch — gracefully degrade
    text = response.text or ""
    return text.strip(), usage


def _default_opinion(agent_key: str) -> dict:
    """Fallback opinion with default/safe parameters."""
    defaults = {key: schema["default"] for key, schema in PARAMETER_SCHEMA.items()}
    return {
        "agent_name": agent_key,
        "provider": "fallback",
        "model": "none",
        "is_fallback": True,
        "latency_ms": 0,
        "parse_status": "default",
        "raw_response_size": 0,
        "confidence": 0.0,  # Zero — no analysis was performed
        "valid_param_ratio": 0.0,  # Zero — no valid parameters from AI
        **defaults,
        "deliberation_minutes": "No minutes generated due to fallback.",
        "rationale": f"Default safe parameters (agent {agent_key} did not respond)",
        "section_overrides": [],
    }


def _weighted_median_merge(opinions: Sequence[dict], analysis_data: dict = None) -> dict:
    """
    Deterministic weighted median merge for parameter adoption.
    Consistent with merge_rule.py's merge logic.

    Rules:
      - Numeric params: weighted median by agent confidence
      - Boolean params: weighted majority vote
    """
    adopted = {}
    if not opinions:
        return {}

    for key, schema in PARAMETER_SCHEMA.items():
        min_v = schema["min"]
        max_v = schema["max"]
        default_v = schema["default"]

        values = []
        weights = []
        for op in opinions:
            values.append(float(op.get(key, default_v)))

            conf = float(op.get("confidence", 0.5))
            valid_ratio = float(op.get("valid_param_ratio", 1.0))

            parse_multiplier = (
                1.0  # JSON format quality does not affect artistic weight
            )

            effective_weight = conf * max(0.25, valid_ratio) * parse_multiplier
            weights.append(effective_weight)

        total_weight = sum(weights) + 1e-6

        is_boolean = min_v == 0 and max_v == 1 and isinstance(default_v, int)

        if is_boolean:
            # Majority vote based on weights
            votes_for = sum(w for v, w in zip(values, weights) if v >= 0.5)
            adopted[key] = 1 if votes_for >= total_weight / 2 else 0
            continue

        # Weighted median (deterministic, non-geometric)
        pairs = sorted(zip(values, weights), key=lambda x: x[0])
        cumulative = 0.0
        median_value = pairs[-1][0]  # fallback
        for val, w in pairs:
            cumulative += w
            if cumulative >= total_weight / 2:
                median_value = val
                break

        # Clamp to bounds
        adopted[key] = round(max(min_v, min(max_v, median_value)), 4)

    # 2. Merge Section Overrides (Dynamic Automation)
    override_votes: dict[str, dict[str, list[tuple[float, float]]]] = {}

    for op in opinions:
        weight = float(op.get("confidence", 0.5)) * max(
            0.25, float(op.get("valid_param_ratio", 1.0))
        )
        for override in op.get("section_overrides", []):
            sec_id = override.get("section_id")
            if not sec_id:
                continue
            if sec_id not in override_votes:
                override_votes[sec_id] = {k: [] for k in PARAMETER_SCHEMA.keys()}
            for k, v in override.items():
                if k in PARAMETER_SCHEMA:
                    try:
                        override_votes[sec_id][k].append((float(v), weight))
                    except (ValueError, TypeError):
                        pass

    final_overrides = []
    for sec_id, param_votes in override_votes.items():
        sec_result: dict[str, Any] = {"section_id": sec_id}
        for k, votes in param_votes.items():
            if not votes:
                continue
            votes.sort(key=lambda x: x[0])
            tot_w = sum(w for _, w in votes) + 1e-6
            cum = 0.0
            med = votes[-1][0]
            for val, w in votes:
                cum += w
                if cum >= tot_w / 2:
                    med = val
                    break
            sec_result[k] = round(
                max(PARAMETER_SCHEMA[k]["min"], min(PARAMETER_SCHEMA[k]["max"], med)), 4
            )

        if len(sec_result) > 1:
            final_overrides.append(sec_result)

    final_overrides.sort(
        key=lambda x: (
            int(re.search(r"\d+", x["section_id"]).group())
            if re.search(r"\d+", x["section_id"])
            else 0
        )
    )
    adopted["section_overrides"] = final_overrides

    # 3. Merge AI-recommended target LUFS / true peak (weighted median across sages)
    for target_key in ("recommended_target_lufs", "recommended_target_true_peak"):
        t_values = []
        t_weights = []
        for op in opinions:
            v = op.get(target_key)
            if v is not None:
                try:
                    t_values.append(float(v))
                    conf = float(op.get("confidence", 0.5))
                    t_weights.append(conf)
                except (ValueError, TypeError):
                    pass
        if t_values:
            total_w = sum(t_weights) + 1e-6
            pairs = sorted(zip(t_values, t_weights), key=lambda x: x[0])
            cumul = 0.0
            median_val = pairs[-1][0]
            for val, w in pairs:
                cumul += w
                if cumul >= total_w / 2:
                    median_val = val
                    break
            adopted[target_key] = round(median_val, 1)



    # Apply signal-measured constraints from Audition's detected_problems
    adopted = _apply_measured_constraints(adopted, analysis_data)

    return adopted


def _apply_measured_constraints(params: dict, analysis_data: dict) -> dict:
    """Apply parameter constraints generated by Vertex AI in Audition.

    Reads `param_guardrails.constraints` from analysis_data.  Each constraint
    is a dict with:
      - param_name: the DSP parameter to constrain
      - constraint_type: "max", "min", or "force"
      - value: the numeric limit

    These constraints are AI-generated based on measured signal characteristics,
    not hardcoded formulas.
    """
    if not analysis_data:
        return params

    guardrails = analysis_data.get("param_guardrails")
    if not guardrails:
        return params

    constraints = guardrails.get("constraints", [])
    if not constraints:
        return params

    p = dict(params)  # shallow copy

    max_constraints: dict[str, float] = {}
    min_constraints: dict[str, float] = {}
    force_constraints: dict[str, float] = {}

    for c in constraints:
        name = c.get("param_name", "")
        ctype = c.get("constraint_type", "")
        val = c.get("value")
        if not name or val is None or not isinstance(val, (int, float)):
            continue
        if ctype == "max":
            if name not in max_constraints or val < max_constraints[name]:
                max_constraints[name] = val
        elif ctype == "min":
            if name not in min_constraints or val > min_constraints[name]:
                min_constraints[name] = val
        elif ctype == "force":
            force_constraints[name] = val

    # Apply force constraints
    for param, val in force_constraints.items():
        if param in p or param in PARAMETER_SCHEMA:
            old = p.get(param)
            p[param] = val
            if old != val:
                logger.info(f"Guardrail[force]: {param} = {val} (was {old})")

    # Apply max constraints
    for param, max_val in max_constraints.items():
        if param in p:
            old = p[param]
            if isinstance(old, (int, float)) and old > max_val:
                p[param] = round(max_val, 4)
                logger.info(f"Guardrail[max]: {param} clamped {old} → {max_val}")

    # Apply min constraints
    for param, min_val in min_constraints.items():
        if param in p:
            old = p[param]
            if isinstance(old, (int, float)) and old < min_val:
                p[param] = round(min_val, 4)
                logger.info(f"Guardrail[min]: {param} clamped {old} → {min_val}")

    # Apply to section_overrides
    overrides = p.get("section_overrides", [])
    if overrides:
        cleaned = []
        for ovr in overrides:
            ovr_copy = dict(ovr)
            for param, max_val in max_constraints.items():
                if param in ovr_copy and isinstance(ovr_copy[param], (int, float)):
                    if ovr_copy[param] > max_val:
                        ovr_copy[param] = round(max_val, 4)
            for param, min_val in min_constraints.items():
                if param in ovr_copy and isinstance(ovr_copy[param], (int, float)):
                    if ovr_copy[param] < min_val:
                        ovr_copy[param] = round(min_val, 4)
            for param, val in force_constraints.items():
                ovr_copy[param] = val
            cleaned.append(ovr_copy)
        p["section_overrides"] = cleaned

    return p


def _calculate_deliberation_score(opinions: Sequence[dict]) -> dict:
    """Decompose agreement into categories for experimental logs."""
    if len(opinions) < 2:
        return {
            "global": 1.0,
            "dynamics": 1.0,
            "tone": 1.0,
            "stereo": 1.0,
            "saturation": 1.0,
        }

    categories = {
        "dynamics": [
            "comp_threshold_db",
            "comp_ratio",
            "comp_attack_sec",
            "comp_release_sec",
            "comp_makeup_db",
            "limiter_ceil_db",
            "limiter_release_ms",
            "input_gain_db",
        ],
        "tone": [
            "eq_low_shelf_gain_db",
            "eq_low_shelf_freq",
            "eq_low_mid_gain_db",
            "eq_low_mid_freq",
            "eq_low_mid_q",
            "eq_high_mid_gain_db",
            "eq_high_mid_freq",
            "eq_high_mid_q",
            "eq_high_shelf_gain_db",
            "eq_high_shelf_freq",
            "dyn_eq_enabled",
        ],
        "stereo": [
            "ms_side_high_gain_db",
            "ms_mid_low_gain_db",
            "stereo_low_mono",
            "stereo_high_wide",
            "stereo_width",
        ],
        "saturation": [
            "transformer_saturation",
            "transformer_mix",
            "triode_drive",
            "triode_bias",
            "triode_mix",
            "tape_saturation",
            "tape_mix",
            "tape_speed",
            "parallel_wet",
            "parallel_drive",
        ],
    }

    agreements = {}
    total_agreements = []

    for cat_name, keys in categories.items():
        cat_agreements = []
        for key in keys:
            if key not in PARAMETER_SCHEMA:
                continue
            values = [op.get(key, 0) for op in opinions]
            schema = PARAMETER_SCHEMA[key]
            param_range = schema["max"] - schema["min"]
            if param_range == 0:
                continue

            spread = max(values) - min(values)
            agreement = max(0.0, 1.0 - (spread / param_range))
            cat_agreements.append(agreement)
            total_agreements.append(agreement)

        agreements[cat_name] = (
            round(sum(cat_agreements) / len(cat_agreements), 3)
            if cat_agreements
            else 0.5
        )

    agreements["global"] = (
        round(sum(total_agreements) / len(total_agreements), 3)
        if total_agreements
        else 0.5
    )
    return agreements


def _get_12_agents_personas() -> dict:
    """ "12 Specialist Agent" Configuration - High resolution parameter negotiation"""
    themes = [
        (
            "High-Frequency Specialist",
            "Focus purely on high-frequency transient enhancement, airiness, and high-shelf EQ management.",
        ),
        (
            "Sub-Bass Specialist",
            "Focus strictly on sub-bass stability. Prevent phase issues below 120Hz. Advocate for low-end monoization.",
        ),
        (
            "Mid-Range Specialist",
            "Focus on the mid-range flow, stereo width in the body of the track, and vocal/lead continuity.",
        ),
        (
            "Harmonic Saturation Specialist",
            "Focus on tube distortion, punch, and clipping. Push triode drive and aggressive harmonic generation safely.",
        ),
        (
            "Acoustic Space Specialist",
            "Focus on acoustic space, reverb tails, and dynamic range preservation. Advocate for minimal compression ratios.",
        ),
        (
            "Transient Specialist",
            "Focus on transient attack times and True Peak limiting. Fast processing, precise compression attacks.",
        ),
        (
            "Warmth Specialist",
            "Focus on low-mid warmth and tape saturation to provide thickness and organic density.",
        ),
        (
            "Stereo Imaging Specialist",
            "Focus entirely on the stereo side channels, evaluating ethereal wideness and mid-side balance.",
        ),
        (
            "Loudness/Center Specialist",
            "Focus on integrated loudness and center channel authority. Dictate overall LUFS gain unconditionally.",
        ),
        (
            "Dynamic EQ Specialist",
            "Focus on surgical dynamic EQ and harshness removal, specifically in the 3kHz-5kHz range.",
        ),
        (
            "Parallel Processing Specialist",
            "Focus on parallel processing (parallel_wet). Recommend hidden compression and saturation without affecting the dry transients.",
        ),
        (
            "Standards & Compliance Specialist",
            "Final arbiter of BS.1770-4 compliance. Verify target LUFS and True Peak limits.",
        ),
    ]

    # Each provider has primary + same-provider fallback (D-09 fix)
    providers = [
        ("openai", "gpt-5.4", "gpt-5.2"),
        ("anthropic", "claude-opus-4-6", "claude-sonnet-4-6"),
        ("google", "gemini-3.1-pro-preview", "gemini-3-flash-preview"),
    ]

    personas = {}
    for i, (name, prompt) in enumerate(themes):
        prov, mod, fallback = providers[i % 3]
        personas[f"agent_{i+1}"] = {
            "name": name,
            "provider": prov,
            "model": mod,
            "fallback_model": fallback,
            "system_prompt": f"You are the {name}. {prompt} Propose mastering parameters based entirely on your domain while respecting physical signal limits.",
        }
    return personas


def _get_ts_envelope_personas() -> dict:
    """Time-Series Specific Evaluators"""
    default_model = os.environ.get("TS_EVALUATOR_MODEL", "gemini-3-flash-preview")
    return {
        "transient_analyst": {
            "name": "Transient Analyst",
            "provider": "google",
            "model": default_model,
            "fallback_model": "gemini-3-flash-preview",
            "system_prompt": "You are the master of the Attack phase. You analyze the first 0-15ms of every percussive hit. You demand precise compressor attacks and high True Peak safety.",
        },
        "sustain_analyst": {
            "name": "Sustain Analyst",
            "provider": "google",
            "model": default_model,
            "fallback_model": "gemini-3-flash-preview",
            "system_prompt": "You govern the body of the sound (15ms-200ms). You demand parallel saturation, Triode drive, and Tape warmth to thicken the sustain.",
        },
        "release_analyst": {
            "name": "Release Analyst",
            "provider": "google",
            "model": default_model,
            "fallback_model": "gemini-3-flash-preview",
            "system_prompt": "You only care about how signals fade. You dictate the breathing of the mix. You demand correct release times on the compressor to match the BPM groove.",
        },
        "macro_dynamic_analyst": {
            "name": "MacroDynamics Analyst",
            "provider": "google",
            "model": default_model,
            "fallback_model": "gemini-3-flash-preview",
            "system_prompt": "You look at the song globally. You manage long-term Integrated LUFS, target dynamic EQ, and ensure the song dynamically grows across sections.",
        },
    }

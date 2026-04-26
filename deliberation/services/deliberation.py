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
    return genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_LOCATION)


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
    4-Step Sequential Pipeline:
      Step 1: Vertex AI produces numbers (already done by Audition upstream)
      Step 2: Claude creates DSP recipe from analysis
      Step 3: ChatGPT + Vertex review/critique the recipe
      Step 4: Claude applies corrections and finalizes

    Returns adopted_params ready for Rendition-DSP.
    """
    # Defensive: ensure analysis_data is a dict
    if isinstance(analysis_data, str):
        try:
            analysis_data = json.loads(analysis_data)
        except (json.JSONDecodeError, TypeError):
            logger.error("analysis_data is a non-parseable string, using empty dict")
            analysis_data = {}
    if not isinstance(analysis_data, dict):
        logger.error(f"analysis_data is {type(analysis_data).__name__}, coercing to empty dict")
        analysis_data = {}

    start_time = time.time()
    all_errors = []
    total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    step_results = {}

    # Build analysis context prompt (shared across steps)
    analysis_prompt = _build_analysis_prompt(
        analysis_data, target_platform, target_lufs, target_true_peak
    )

    # ── STEP 2: Claude creates DSP recipe ──
    logger.info("=== STEP 2: Claude — DSPレシピ作成 ===")
    claude_model = os.environ.get("RECIPE_CLAUDE_MODEL", "claude-opus-4-7")
    claude_fallback = os.environ.get("RECIPE_CLAUDE_FALLBACK", "claude-opus-4-7")

    draft_text, draft_usage = await _call_with_fallback(
        primary_provider="anthropic", primary_model=claude_model,
        fallback_provider="anthropic", fallback_model=claude_fallback,
        system_prompt=_STEP2_SYSTEM_PROMPT,
        user_prompt=analysis_prompt + "\n\nRespond with a JSON object only.",
        errors=all_errors, step_name="step2_claude_draft",
    )
    _accumulate_tokens(total_tokens, draft_usage)

    draft_parse = _robust_json_parse(draft_text)
    draft_params = draft_parse["parsed"]
    if not draft_params:
        logger.error("Step 2 failed: Claude returned no usable params, using defaults")
        draft_params = {k: v["default"] for k, v in PARAMETER_SCHEMA.items()}

    step_results["step2_draft"] = {
        "provider": "anthropic", "model": claude_model,
        "parse_status": draft_parse["status"],
        "param_count": len([k for k in draft_params if k in PARAMETER_SCHEMA]),
    }
    logger.info(f"Step 2 complete: {len(draft_params)} params in draft")

    # ── STEP 3: ChatGPT + Vertex review in parallel ──
    logger.info("=== STEP 3: ChatGPT + Vertex — ダメ出し ===")
    review_prompt = _build_review_prompt(analysis_prompt, draft_params)

    gpt_model = os.environ.get("REVIEW_GPT_MODEL", "gpt-4.1")
    gpt_fallback = os.environ.get("REVIEW_GPT_FALLBACK", "gpt-4.1-mini")
    vertex_model = os.environ.get("REVIEW_VERTEX_MODEL", "gemini-2.5-flash")
    vertex_fallback = os.environ.get("REVIEW_VERTEX_FALLBACK", "gemini-2.5-flash")

    review_tasks = [
        _call_with_fallback(
            "openai", gpt_model, "openai", gpt_fallback,
            _STEP3_REVIEW_SYSTEM_PROMPT, review_prompt,
            all_errors, "step3_chatgpt_review",
        ),
        _call_with_fallback(
            "google", vertex_model, "google", vertex_fallback,
            _STEP3_REVIEW_SYSTEM_PROMPT, review_prompt,
            all_errors, "step3_vertex_review",
        ),
    ]
    review_results = await asyncio.gather(*review_tasks, return_exceptions=True)

    reviews = []
    for i, res in enumerate(review_results):
        reviewer = "chatgpt" if i == 0 else "vertex"
        if isinstance(res, Exception):
            logger.error(f"Step 3 {reviewer} failed: {res}")
            reviews.append({"reviewer": reviewer, "issues": [], "error": str(res)})
        else:
            text, usage = res
            _accumulate_tokens(total_tokens, usage)
            parsed = _robust_json_parse(text)
            review_data = parsed["parsed"] if isinstance(parsed["parsed"], dict) else {}
            review_data["reviewer"] = reviewer
            reviews.append(review_data)

    step_results["step3_reviews"] = [
        {"reviewer": r.get("reviewer"), "issue_count": len(r.get("issues", r.get("problems", [])))}
        for r in reviews
    ]
    logger.info(f"Step 3 complete: {len(reviews)} reviews collected")

    # ── STEP 4: Claude applies corrections ──
    logger.info("=== STEP 4: Claude — 修正・最終化 ===")
    fix_model = os.environ.get("FIX_CLAUDE_MODEL", "claude-opus-4-7")
    fix_fallback = os.environ.get("FIX_CLAUDE_FALLBACK", "claude-opus-4-7")
    fix_prompt = _build_fix_prompt(analysis_prompt, draft_params, reviews)

    final_text, final_usage = await _call_with_fallback(
        "anthropic", fix_model, "anthropic", fix_fallback,
        _STEP4_FIX_SYSTEM_PROMPT,
        fix_prompt + "\n\nRespond with a JSON object only.",
        all_errors, "step4_claude_fix",
    )
    _accumulate_tokens(total_tokens, final_usage)

    final_parse = _robust_json_parse(final_text)
    final_params = final_parse["parsed"]
    if not final_params:
        logger.warning("Step 4 failed: using draft params from Step 2")
        final_params = draft_params

    # Clamp all params to schema bounds
    adopted = _clamp_to_schema(final_params)

    # Apply signal-measured constraints from Audition
    adopted = _apply_measured_constraints(adopted, analysis_data)

    runtime_ms = int((time.time() - start_time) * 1000)
    query_hash = hashlib.sha256(analysis_prompt.encode()).hexdigest()

    pipeline_summary = (
        f"4-Step Sequential Pipeline completed in {runtime_ms}ms. "
        f"Claude drafted {len(draft_params)} params → "
        f"ChatGPT+Vertex reviewed with {sum(len(r.get('issues', r.get('problems', []))) for r in reviews)} issues → "
        f"Claude finalized {len(adopted)} params."
    )

    return {
        "run_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, query_hash)),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trivium_summary": pipeline_summary,
        "query_hash": query_hash,
        "analysis_version": "v3_4step",
        "schema_version": "2.0",
        "sage_config": sage_config or {},
        "pipeline_mode": "4step_sequential",
        "step_results": step_results,
        "provider_results": {
            "step2_claude": {"provider": "anthropic", "model": claude_model},
            "step3_chatgpt": {"provider": "openai", "model": gpt_model},
            "step3_vertex": {"provider": "google", "model": vertex_model},
            "step4_claude": {"provider": "anthropic", "model": fix_model},
        },
        "merge_strategy": "4step_review_and_fix",
        "runtime_ms": runtime_ms,
        "token_usage": total_tokens,
        "errors": all_errors,
        "draft_params": draft_params,
        "reviews": reviews,
        "opinions": [{"agent_name": "claude_final", "provider": "anthropic",
                       "model": fix_model, **adopted,
                       "confidence": float(final_params.get("confidence", 0.85)),
                       "rationale": final_params.get("rationale", ""),
                       "deliberation_minutes": final_params.get("deliberation_minutes", ""),
                       "section_overrides": final_params.get("section_overrides", adopted.get("section_overrides", [])),
                       }],
        "adopted_params": adopted,
        "deliberation_score": float(final_params.get("confidence", 0.85)),
        "deliberation_score_detail": {"global": float(final_params.get("confidence", 0.85))},
        "target_lufs": target_lufs,
        "target_true_peak": target_true_peak,
    }


# ──────────────────────────────────────────
# Step-specific system prompts
# ──────────────────────────────────────────
_STEP2_SYSTEM_PROMPT = """You are a world-class mastering engineer (Claude).
Your job: Read the audio analysis data and CREATE a complete DSP recipe.
You must output ALL DSP parameters as a JSON object.
Be bold and creative — propose the BEST possible mastering for this specific track.
Do NOT play it safe with defaults. Every parameter must reflect deep sonic analysis."""

_STEP3_REVIEW_SYSTEM_PROMPT = """You are a critical audio mastering reviewer.
Your job: Review the proposed DSP recipe against the audio analysis.
Find problems, contradictions, and missed opportunities.
Output a JSON object with:
- "issues": list of {"param": "param_name", "problem": "description", "suggestion": "fix"}
- "severity": "critical" | "warning" | "minor"
- "overall_score": 0-100 (quality of the draft)
- "summary": brief review summary
Be HARSH and SPECIFIC. Point out every problem you see."""

_STEP4_FIX_SYSTEM_PROMPT = """You are a world-class mastering engineer (Claude).
Your job: Take the draft DSP recipe AND the reviewer feedback, then produce the FINAL corrected recipe.
Address every critical and warning issue raised by the reviewers.
Output the complete corrected JSON with ALL DSP parameters.
Include "changes_made": list of what you fixed and why."""


def _build_review_prompt(analysis_prompt: str, draft_params: dict) -> str:
    """Build the review prompt for Step 3 (ChatGPT + Vertex)."""
    return f"""{analysis_prompt}

---

## DRAFT DSP RECIPE (from Claude, Step 2)
The following DSP parameters were proposed. Review them critically.

```json
{json.dumps(draft_params, indent=2, default=str)}
```

Review each parameter against the analysis data. Find:
1. Parameters that contradict the analysis (e.g., boosting harsh frequencies)
2. Parameters that are too conservative (missed opportunities)
3. Parameters that conflict with each other
4. Missing section_overrides for distinct sections
5. Inappropriate target LUFS/True Peak for the genre

Respond with JSON only."""


def _build_fix_prompt(analysis_prompt: str, draft_params: dict, reviews: list) -> str:
    """Build the fix prompt for Step 4 (Claude finalize)."""
    reviews_text = json.dumps(reviews, indent=2, default=str)
    return f"""{analysis_prompt}

---

## YOUR DRAFT (Step 2)
```json
{json.dumps(draft_params, indent=2, default=str)}
```

## REVIEWER FEEDBACK (Step 3 — ChatGPT + Vertex)
```json
{reviews_text}
```

Based on the reviewer feedback, produce the FINAL corrected DSP recipe.
Address every critical and warning issue. Keep parameters that were approved.
Include ALL parameters from the schema. Respond with JSON only."""


async def _call_with_fallback(
    primary_provider: str, primary_model: str,
    fallback_provider: str, fallback_model: str,
    system_prompt: str, user_prompt: str,
    errors: list, step_name: str,
) -> tuple[str, dict]:
    """Call an LLM with fallback. Returns (text, token_usage)."""
    attempts = [(primary_provider, primary_model)]
    if fallback_model and fallback_model != primary_model:
        attempts.append((fallback_provider, fallback_model))

    for prov, model in attempts:
        key_pool = _openai_keys if prov == "openai" else _anthropic_keys if prov == "anthropic" else _google_keys
        for key_idx in range(max(1, len(key_pool))):
            try:
                if prov == "openai":
                    return await _call_openai(model, system_prompt, user_prompt, key_idx)
                elif prov == "anthropic":
                    return await _call_anthropic(model, system_prompt, user_prompt, key_idx)
                else:
                    return await _call_google(model, system_prompt, user_prompt, key_idx)
            except Exception as e:
                errors.append({
                    "step": step_name, "provider": prov, "model": model,
                    "message": str(e), "severity": "warning",
                })
                logger.warning(f"[{step_name}] {prov}/{model} key[{key_idx}] failed: {e}")

    errors.append({"step": step_name, "message": "All attempts failed", "severity": "error"})
    return "{}", {}


def _accumulate_tokens(total: dict, usage: dict):
    """Add token usage to running total."""
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        total[k] = total.get(k, 0) + usage.get(k, 0)


def _clamp_to_schema(params: dict) -> dict:
    """Clamp all parameters to PARAMETER_SCHEMA bounds."""
    adopted = {}
    for key, schema in PARAMETER_SCHEMA.items():
        if key in params:
            try:
                val = float(params[key])
                if math.isnan(val) or math.isinf(val):
                    val = schema["default"]
            except (ValueError, TypeError):
                val = schema["default"]
            adopted[key] = round(max(schema["min"], min(schema["max"], val)), 4)
        else:
            adopted[key] = schema["default"]

    # Pass through non-schema fields
    for key in ("recommended_target_lufs", "recommended_target_true_peak"):
        if key in params:
            adopted[key] = params[key]

    # Defensive: normalize section_overrides
    raw_overrides = params.get("section_overrides", [])
    if isinstance(raw_overrides, str):
        try:
            raw_overrides = json.loads(raw_overrides)
        except (json.JSONDecodeError, TypeError):
            raw_overrides = []
    if not isinstance(raw_overrides, list):
        raw_overrides = []
    clean_overrides = []
    for ovr in raw_overrides:
        if isinstance(ovr, str):
            try:
                ovr = json.loads(ovr)
            except (json.JSONDecodeError, TypeError):
                continue
        if isinstance(ovr, dict):
            clean_overrides.append(ovr)
    adopted["section_overrides"] = clean_overrides

    return adopted


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

        detected_genre = track_id.get('genre', 'Unknown')
        detected_mood = track_id.get('mood', 'Unknown')

        return f"""## Formplan-Guided RENDITION_DSP Parameter Selection

### Domain
Detected Genre: **{detected_genre}** | Mood: **{detected_mood}**
You are mastering this track to compete with the **current global chart Top 10** in the {detected_genre} genre. Study what makes the best {detected_genre} masters in the world sound extraordinary — the depth, punch, width, clarity, and emotional impact — and replicate that level of craftsmanship for THIS track.

### Target
- Platform: {platform}
- **YOU MUST DECIDE the optimal target LUFS and target True Peak for this specific track.** Include `"recommended_target_lufs"` (float) and `"recommended_target_true_peak"` (float, in dBTP) in your JSON response. Base your decision on what the TOP MASTERING ENGINEERS in {detected_genre} would choose for this specific track's dynamics, energy, and intended listening context.

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
You are a world-class mastering engineer whose work regularly places in the **Billboard / Spotify / Apple Music Top 10** for {detected_genre}. Your mastering is renowned for its **繊細さ (delicacy)** — the ability to maximize sonic impact through precise, nuanced parameter choices rather than brute force.

For EVERY parameter:
1. Consider the track's unique sonic fingerprint — its transients, harmonics, spatial characteristics
2. Find the **optimal point** that maximizes the track's emotional impact and competitive loudness
3. Shape EQ frequencies and Q values **specifically for this track's spectral content** — never use generic center frequencies
4. Apply **dynamic, section-by-section automation** that breathes with the music's structure
5. Every choice must be justified as: "This is what a Grammy-winning {detected_genre} master sounds like"

Do NOT play it safe. Do NOT use generic defaults. Every parameter must reflect deep listening and intentional sonic design.

Based on this formplan, propose optimal RENDITION_DSP parameters.
The formplan targets tell you WHAT to achieve. You decide HOW via RENDITION_DSP params.

**SECTION-BY-SECTION DYNAMIC MASTERING**: Each section demands unique treatment. Drops need different EQ/compression than verses. Breakdowns need different stereo width than buildups. YOU MUST apply per-section automation via `section_overrides`, including per-section EQ frequencies, compression settings, saturation amounts, and stereo imaging.

Respond with a JSON object containing ALL parameters listed below.

Full RENDITION_DSP parameters (YOU MUST specify ALL of these):
- input_gain_db (-6 to 12): Input gain adjustment
- eq_low_shelf_gain_db (-6 to 6), eq_low_shelf_freq (30-200): Low shelf EQ
- eq_low_mid_gain_db (-6 to 6), eq_low_mid_freq (100-1000), eq_low_mid_q (0.3-5.0): Low-mid parametric EQ
- eq_high_mid_gain_db (-6 to 6), eq_high_mid_freq (1000-8000), eq_high_mid_q (0.3-5.0): High-mid parametric EQ
- eq_high_shelf_gain_db (-6 to 6), eq_high_shelf_freq (5000-18000): High shelf EQ
- ms_side_high_gain_db (-3 to 3), ms_mid_low_gain_db (-3 to 3): M/S balance
- comp_threshold_db (-24 to 0), comp_ratio (1.0-6.0): Compressor
- comp_attack_sec (0.001-0.1), comp_release_sec (0.05-0.5), comp_makeup_db (0-12): Compressor timing/makeup
- limiter_ceil_db (-0.3 to -0.1), limiter_release_ms (10-200): Limiter
- transformer_saturation (0-1.0), transformer_mix (0-1.0): Transformer saturation
- triode_drive (0-1.0), triode_bias (-2.0 to 0.0), triode_mix (0-1.0): Tube saturation
- tape_saturation (0-1.0), tape_mix (0-1.0), tape_speed (7.5-30.0): Tape saturation
- dyn_eq_enabled (0 or 1): Dynamic EQ
- stereo_low_mono (0-1.0), stereo_high_wide (0.8-1.5), stereo_width (0.8-1.3): Stereo imaging
- parallel_wet (0-0.5), parallel_drive (0-5.0): Parallel processing

**CRITICAL**: The `Parameter Guardrails` section contains constraints derived from the actual signal measurements by the upstream analysis AI. You MUST respect these constraints.

Additionally include:
- **\"recommended_target_lufs\"** (float, REQUIRED): The loudness target that would make this track competitive in the {detected_genre} Top 10.
- **\"recommended_target_true_peak\"** (float, dBTP, REQUIRED): The true peak ceiling optimal for this track's transient character.
- A "deliberation_minutes" string (minimum 400 characters) containing detailed meeting minutes (議事録).
- A "rationale" string (minimum 200 characters) summarizing your reasoning.
- A "confidence" float (0-1)
- "section_overrides": Per-section parameter automation. REQUIRED for multi-section tracks.
  Format: [{{"section_id": "SEC_0_Intro", "stereo_width": 1.0, "eq_high_mid_freq": 2500}}, ...]
  Match "section_id" EXACTLY with the provided Sections.
  FAILURE TO PROVIDE section_overrides IS A CRITICAL ERROR.

Keep ALL parameters within these ranges:
{json.dumps({k: {"min": v["min"], "max": v["max"]} for k, v in PARAMETER_SCHEMA.items()}, indent=2)}
"""

    # Legacy v1 format fallback
    detected_genre = track_id.get('genre', 'Unknown')
    detected_mood = track_id.get('mood', 'Unknown')

    return f"""## Audio Analysis Report — World-Class {detected_genre} Mastering

### Domain
Detected Genre: **{detected_genre}** | Mood: **{detected_mood}**
You are mastering this track to compete with the **current global chart Top 10** in {detected_genre}. Your goal: a master so refined it is indistinguishable from the best commercial releases in this genre.

### Target
- Platform: {platform}
- **YOU MUST DECIDE the optimal target LUFS and target True Peak.** Base your decision on what the TOP MASTERING ENGINEERS in {detected_genre} would choose for this specific track.

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
You are a world-class mastering engineer whose {detected_genre} masters regularly chart in the **Top 10 globally**. Your signature is **繊細な動的マスタリング (delicate dynamic mastering)** — achieving maximum sonic impact through precise, nuanced choices.

For EVERY parameter:
1. Analyze this track's unique spectral and dynamic fingerprint
2. Choose EQ frequencies and Q values **specifically tuned to this track's content** — never generic
3. Apply **section-by-section dynamic automation** that breathes with the music
4. Every choice = "This is what a Grammy-winning {detected_genre} master sounds like"

Respond with a JSON object containing ALL parameters.

Full RENDITION_DSP parameters (ALL required):
- input_gain_db, eq_low_shelf_gain_db, eq_low_shelf_freq
- eq_low_mid_gain_db, eq_low_mid_freq, eq_low_mid_q
- eq_high_mid_gain_db, eq_high_mid_freq, eq_high_mid_q
- eq_high_shelf_gain_db, eq_high_shelf_freq
- ms_side_high_gain_db, ms_mid_low_gain_db
- comp_threshold_db, comp_ratio, comp_attack_sec, comp_release_sec, comp_makeup_db
- limiter_ceil_db, limiter_release_ms
- transformer_saturation, transformer_mix
- triode_drive, triode_bias, triode_mix
- tape_saturation, tape_mix, tape_speed
- dyn_eq_enabled, stereo_low_mono, stereo_high_wide, stereo_width
- parallel_wet, parallel_drive

**CRITICAL**: Respect Parameter Guardrails from signal analysis.

Additionally include:
- **"recommended_target_lufs"** (float, REQUIRED): Competitive loudness for {detected_genre} Top 10.
- **"recommended_target_true_peak"** (float, dBTP, REQUIRED): Optimal ceiling for this track.
- "deliberation_minutes" (string, min 400 chars): Detailed reasoning.
- "rationale" (string, min 200 chars)
- "confidence" (float, 0-1)
- "section_overrides": Per-section automation. REQUIRED for multi-section tracks.

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

        # Defensive: AnthropicVertex rawPredict may return different content types
        content = response.content
        if not content:
            return "", usage

        first_block = content[0]
        # Standard Anthropic SDK returns TextBlock objects with .text attribute
        if hasattr(first_block, "text"):
            text = first_block.text
        elif isinstance(first_block, dict):
            # AnthropicVertex rawPredict may return dicts
            text = first_block.get("text", json.dumps(first_block))
        elif isinstance(first_block, str):
            text = first_block
        else:
            text = str(first_block)

        return text or "", usage

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

    # Defensive: ensure analysis_data is a dict
    if isinstance(analysis_data, str):
        try:
            analysis_data = json.loads(analysis_data)
        except (json.JSONDecodeError, TypeError):
            analysis_data = {}
    if not isinstance(analysis_data, dict):
        analysis_data = {}

    # Defensive: filter out non-dict opinions
    opinions = [op for op in opinions if isinstance(op, dict)]
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
        if not isinstance(op, dict):
            continue
        weight = float(op.get("confidence", 0.5)) * max(
            0.25, float(op.get("valid_param_ratio", 1.0))
        )
        overrides_raw = op.get("section_overrides", [])
        if isinstance(overrides_raw, str):
            try:
                overrides_raw = json.loads(overrides_raw)
            except (json.JSONDecodeError, TypeError):
                overrides_raw = []
        if not isinstance(overrides_raw, list):
            overrides_raw = []
        for override in overrides_raw:
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
    if isinstance(overrides, str):
        try:
            overrides = json.loads(overrides)
        except (json.JSONDecodeError, TypeError):
            overrides = []
    if overrides:
        cleaned = []
        for ovr in overrides:
            if isinstance(ovr, str):
                try:
                    ovr = json.loads(ovr)
                except (json.JSONDecodeError, TypeError):
                    continue
            if not isinstance(ovr, dict):
                continue
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

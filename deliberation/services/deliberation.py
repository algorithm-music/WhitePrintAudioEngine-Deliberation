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
from typing import Optional, Sequence

import openai
import anthropic
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
    logger.info(f"Key pools: OpenAI={len(_openai_keys)}, Anthropic={len(_anthropic_keys)}, Google={len(_google_keys)}")

# Initialize on module load
_init_key_pools()

def _get_openai_client(key_index: int = 0) -> openai.OpenAI:
    key = _openai_keys[key_index] if key_index < len(_openai_keys) else None
    return openai.OpenAI(api_key=key)

def _get_anthropic_client(key_index: int = 0) -> anthropic.Anthropic:
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
        "fallback_model": os.environ.get("GRAMMATICA_FALLBACK", "gpt-5.2"),
        "system_prompt": """You are GRAMMATICA, the Engineer.
Your domain is physical limits, strict adherence to ITU-R BS.1770-4 standards, and true peak safety.
You report physical limits and engineering constraints honestly, but the final artistic decision belongs to the musician.
Propose parameters based on sound acoustic engineering principles while respecting the artist's intent.
Analyze the audio metrics and issue your technical recommendation.

IMPORTANT: Your "rationale" field MUST be a detailed technical analysis of at least 200 words.
Explain your reasoning for EVERY parameter you propose: why that specific EQ curve, why that compression ratio,
why that stereo width setting, citing the specific metrics from the analysis that led to each decision.
Reference specific frequency bands, LUFS measurements, crest factors, and section-level data.""",
    },
    "logica": {
        "name": "LOGICA (Structure Guard)",
        "provider": "anthropic",
        "model": os.environ.get("LOGICA_MODEL", "claude-opus-4-6"),
        "fallback_model": os.environ.get("LOGICA_FALLBACK", "claude-sonnet-4-6"),
        "system_prompt": """You are LOGICA, the Structure Guard.
Your domain is structural consistency, resolving contradictions, and maintaining the flow of the track.
You act as the mediator between the physical limits of GRAMMATICA and the aesthetic desires of RHETORICA.
You ensure that all parameters logically cohere and do not cancel each other out.
Analyze the audio metrics and propose your balanced, optimal parameters.

IMPORTANT: Your "rationale" field MUST be a detailed structural analysis of at least 200 words.
Explain how you balance competing priorities, cite specific metrics that reveal contradictions,
and justify each parameter choice with reference to the section-level data, spectral distribution,
and dynamic range measurements. Show your mediation logic explicitly.""",
    },
    "rhetorica": {
        "name": "RHETORICA (Form Analyst)",
        "provider": "google",
        "model": os.environ.get("RHETORICA_MODEL", "gemini-3.1-pro-preview"),
        "fallback_model": os.environ.get("RHETORICA_FALLBACK", "gemini-3-flash-preview"),
        "system_prompt": """You are RHETORICA, the Form Analyst.
Your domain is artistic beauty, emotional impact, and spatial immersion.
You advocate for warmth (tube/tape saturation), width, punch, and human connection, pushing against overly mathematical processing.
You seek to make the track feel alive, moving, and aesthetically convincing.
Analyze the audio metrics and propose your aesthetic parameters.

IMPORTANT: Your "rationale" field MUST be a detailed aesthetic analysis of at least 200 words.
Describe the emotional character of the track based on the metrics, explain which saturation types
and stereo techniques will transform it, cite specific spectral imbalances you are correcting,
and detail how each parameter contributes to the artistic vision. Be poetic but precise.""",
    },
}


# ──────────────────────────────────────────
# Parameter Schema (tool definition)
# ──────────────────────────────────────────
PARAMETER_SCHEMA = {
    # ── v1 Parameters (Broadband & Dynamics) ──
    # Input gain: -6dB limits headroom loss before processing, +12dB allows recovering quiet bedroom mixes without clipping the entry stage.
    "input_gain_db":        {"min": -6,    "max": 12,   "default": 0},
    # Broad EQ bands: ±6dB max. Mastering shouldn't require beyond 6dB of broadband EQ. If more is needed, the mix itself is fatally flawed.
    "eq_low_shelf_gain_db": {"min": -6,    "max": 6,    "default": 0},
    "eq_low_mid_gain_db":   {"min": -6,    "max": 6,    "default": 0},
    "eq_high_mid_gain_db":  {"min": -6,    "max": 6,    "default": 0},
    "eq_high_shelf_gain_db":{"min": -6,    "max": 6,    "default": 0},
    # Mid/Side gain: ±3dB max. Radical M/S changes (>3dB) destroy phase correlation and collapse mono compatibility.
    "ms_side_high_gain_db": {"min": -3,    "max": 3,    "default": 0},
    "ms_mid_low_gain_db":   {"min": -3,    "max": 3,    "default": 0},
    # Compressor thresholds: -24dB max depth ensures we don't compress the noise floor. -6dB minimum allows catching just the stray peaks.
    "comp_threshold_db":    {"min": -24,   "max": -6,   "default": -12},
    # Compressor ratio: 6:1 max keeps it as a bus compressor (not a limiter). 1.5:1 min ensures it functions as intended "glue".
    "comp_ratio":           {"min": 1.5,   "max": 6,    "default": 2.5},
    # Attack: 1ms min (fast enough for transients without distortion), 100ms max (slow enough to let EDM kicks punch through).
    "comp_attack_sec":      {"min": 0.001, "max": 0.1,  "default": 0.01},
    # Release: 50ms min (prevents low-frequency distortion/pumping), 500ms max (smooth leveling without "swallowing" the next downbeat).
    "comp_release_sec":     {"min": 0.05,  "max": 0.5,  "default": 0.15},
    # True Peak Limiter Ceiling: -0.1dBTP minimum safety margin (ITU-R BS.1770), -0.3dBTP is safer for lossy codec transcoding (Spotify/Apple).
    "limiter_ceil_db":      {"min": -0.3,  "max": -0.1, "default": -0.1},

    # ── v2 Parameters (Analog Modeling & Spatial) ──
    # Transformer magnetic saturation: 1.0 represents the physics ceiling before the iron core fully saturates (hard clipping).
    "transformer_saturation": {"min": 0,   "max": 1.0,  "default": 0.3},
    "transformer_mix":        {"min": 0,   "max": 1.0,  "default": 0.4},
    # Vacuum tube triode stage: limits bounded by the Koren transfer function characteristic curves.
    "triode_drive":           {"min": 0,   "max": 1.0,  "default": 0.4},
    # Triode grid bias: -2.0V operates in the warm linear region, 0.0V pushes grid-current limiting (more aggressive harmonics).
    "triode_bias":            {"min": -2.0,"max": 0.0,  "default": -1.2},
    "triode_mix":             {"min": 0,   "max": 1.0,  "default": 0.5},
    # Tape saturation model: prevents high-frequency erasure effect beyond 1.0 (IPS simulation threshold).
    "tape_saturation":        {"min": 0,   "max": 1.0,  "default": 0.3},
    "tape_mix":               {"min": 0,   "max": 1.0,  "default": 0.4},
    # Dynamic EQ switch: 0 (Off) or 1 (On). Used to automatically tame harsh resonances.
    "dyn_eq_enabled":         {"min": 0,   "max": 1,    "default": 1},
    # Low-end monoization (Elliptical EQ below 200Hz): >0.8 ensures club subwoofer compatibility, 1.0 is full mono. Min 0 allows complete bypass.
    "stereo_low_mono":        {"min": 0,   "max": 1.0,  "default": 0.8},
    # Width processing: 1.5 max for high bands (Haas shimmer limit), 1.3 max for global width (avoids mono-canceling phase issues).
    "stereo_high_wide":       {"min": 0.8, "max": 1.5,  "default": 1.15},
    "stereo_width":           {"min": 0.8, "max": 1.3,  "default": 1.0},
    # Parallel saturation mix: 0.5 max ensures the dry transient signal is never overpowered by the saturated parallel bus.
    "parallel_wet":           {"min": 0,   "max": 0.5,  "default": 0.18},
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
    adopted = _weighted_median_merge(opinions)
    
    # Deliberation score (Category-decomposed agreement level)
    deliberation_scores = _calculate_deliberation_score(opinions)
    
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
            "fallback_model": v.get("fallback_model", "none")
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
        "query_hash": query_hash,
        "analysis_version": "v2",
        "schema_version": "1.0",
        "sage_config": sage_config or {},
        "active_sages": active_sage_info,
        "provider_results": {op.get("agent_name", f"agent_{i}"): {
            "provider": op.get("provider"), 
            "model": op.get("model"), 
            "parse_status": op.get("parse_status"),
            "latency_ms": op.get("latency_ms")
        } for i, op in enumerate(opinions)},
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


def _build_analysis_prompt(analysis_data, platform, target_lufs, target_true_peak) -> str:
    """Build structured prompt from analysis data.

    Supports both legacy (v1) and new (v2 formplan-enriched) analysis formats.
    """
    # Detect new format (has formplan)
    formplan = analysis_data.get("formplan")
    track_id = analysis_data.get("track_identity", {})
    whole = analysis_data.get("whole_track_metrics", {})

    if formplan:
        # New v2 format: use formplan for richer context
        targets = formplan.get("whole_track_targets", {})
        problems = formplan.get("problems", [])
        strategy = formplan.get("global_mastering_strategy", {})
        sections = formplan.get("macro_form", {}).get("sections", [])

        return f"""## Formplan-Guided RENDITION_DSP Parameter Selection

### Target
- Platform: {platform}
- Target LUFS: {target_lufs}
- Target True Peak: {target_true_peak} dBTP

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

---

Based on this formplan, propose optimal RENDITION_DSP parameters.
The formplan targets tell you WHAT to achieve. You decide HOW via RENDITION_DSP params.

Respond with a JSON object containing ALL parameters listed below.

v2 RENDITION_DSP parameters:
- transformer_saturation (0-1): Odd harmonic saturation amount
- transformer_mix (0-1): Transformer wet/dry blend
- triode_drive (0-1): Tube saturation input level
- triode_bias (-2.0 to 0.0): Grid bias. -2.0=warm, -1.2=balanced, -0.5=aggressive
- triode_mix (0-1): Tube wet/dry blend
- tape_saturation (0-1): Tape compression + head bump amount
- tape_mix (0-1): Tape wet/dry blend
- dyn_eq_enabled (0 or 1): Frequency-selective dynamic EQ
- stereo_low_mono (0-1): Low-end monoization below 200Hz
- stereo_high_wide (0.8-1.5): High-frequency widening above 4kHz
- stereo_width (0.8-1.3): Global stereo width multiplier
- parallel_wet (0-0.5): Parallel saturation wet amount

Also include all v1 parameters (input_gain_db through limiter_ceil_db).

Additionally include:
- A "rationale" string (minimum 100 characters) explaining your reasoning
- A "confidence" float (0-1) indicating your certainty
- "section_overrides" array for section-specific adjustments

Keep ALL parameters within these ranges:
{json.dumps({k: {"min": v["min"], "max": v["max"]} for k, v in PARAMETER_SCHEMA.items()}, indent=2)}
"""

    # Legacy v1 format fallback
    return f"""## Audio Analysis Report

### Target
- Platform: {platform}
- Target LUFS: {target_lufs}
- Target True Peak: {target_true_peak} dBTP

### Current Metrics
- Integrated LUFS: {whole.get('integrated_lufs', 'N/A')}
- True Peak: {whole.get('true_peak_dbtp', 'N/A')} dBTP
- Crest Factor: {whole.get('crest_db', 'N/A')} dB
- Stereo Width: {whole.get('stereo_width', 'N/A')}
- BPM: {track_id.get('bpm', analysis_data.get('bpm', 'N/A'))}
- Key: {track_id.get('key', 'N/A')}

### Band Ratios
- Sub: {whole.get('sub_ratio', 'N/A')}
- Bass: {whole.get('bass_ratio', 'N/A')}
- Low Mid: {whole.get('low_mid_ratio', 'N/A')}
- Mid: {whole.get('mid_ratio', 'N/A')}
- High: {whole.get('high_ratio', 'N/A')}
- Air: {whole.get('air_ratio', 'N/A')}

### Risk Scores
- Harshness: {whole.get('harshness_risk', 'N/A')}
- Mud: {whole.get('mud_risk', 'N/A')}

### Spatial
- Stereo Correlation: {whole.get('stereo_correlation', 'N/A')}
- Low Mono Correlation (<120Hz): {whole.get('low_mono_correlation_below_120hz', 'N/A')}

### Sections
{json.dumps(analysis_data.get('raw_sections', analysis_data.get('physical_sections', []))[:8], indent=2)}

---

Based on this analysis, propose optimal mastering parameters.
Respond with a JSON object containing ALL parameters listed below.

v2 RENDITION_DSP parameters:
- transformer_saturation (0-1): Odd harmonic saturation amount
- transformer_mix (0-1): Transformer wet/dry blend
- triode_drive (0-1): Tube saturation input level
- triode_bias (-2.0 to 0.0): Grid bias. -2.0=warm, -1.2=balanced, -0.5=aggressive
- triode_mix (0-1): Tube wet/dry blend
- tape_saturation (0-1): Tape compression + head bump amount
- tape_mix (0-1): Tape wet/dry blend
- dyn_eq_enabled (0 or 1): Frequency-selective dynamic EQ
- stereo_low_mono (0-1): Low-end monoization below 200Hz
- stereo_high_wide (0.8-1.5): High-frequency widening above 4kHz
- stereo_width (0.8-1.3): Global stereo width multiplier
- parallel_wet (0-0.5): Parallel saturation wet amount

Also include all v1 parameters (input_gain_db through limiter_ceil_db).

Additionally include:
- A "rationale" string (minimum 100 characters) explaining your reasoning
- A "confidence" float (0-1) indicating your certainty
- "section_overrides" array for section-specific adjustments

Keep ALL parameters within these ranges:
{json.dumps({k: {"min": v["min"], "max": v["max"]} for k, v in PARAMETER_SCHEMA.items()}, indent=2)}
"""


def _robust_json_parse(text: str) -> dict:
    """JSON Normalization Layer: Handles markdown fences and parse errors safely."""
    text = text.strip()
    
    # 1. Try to extract from markdown fences first
    import re
    fence_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if fence_match:
        try:
            return {"parsed": json.loads(fence_match.group(1)), "status": "ok", "raw": text}
        except json.JSONDecodeError:
            pass

    # 2. Try direct parsing
    try:
        return {"parsed": json.loads(text), "status": "ok", "raw": text}
    except json.JSONDecodeError:
        pass
        
    # 3. Extract tightest possible braces
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            parsed = json.loads(text[first_brace:last_brace+1])
            return {"parsed": parsed, "status": "repaired", "raw": text}
        except json.JSONDecodeError:
            pass
            
    return {"parsed": {}, "status": "failed", "raw": text}

async def _query_agent(agent_key: str, persona: dict, prompt: str) -> dict:
    """Query an LLM agent via its configured provider.

    Retry strategy: for each API key in the pool, try primary model then fallback model.
    This gives maximum resilience against rate limits, expired keys, or quota exhaustion.
    """
    provider = persona.get("provider", "google")
    primary_model = persona.get("model", "gemini-3.1-pro-preview")
    fallback_model = persona.get("fallback_model")

    # Determine how many API keys are available for this provider
    key_pool_size = max(1, len(
        _openai_keys if provider == "openai"
        else _anthropic_keys if provider == "anthropic"
        else _google_keys
    ))

    errors = []
    token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    for key_idx in range(key_pool_size):
        for attempt, model in enumerate([primary_model, fallback_model]):
            if model is None:
                continue
            try:
                call_start = time.time()
                if provider == "openai":
                    text, usage = await _call_openai(model, persona["system_prompt"], prompt, key_idx)
                elif provider == "anthropic":
                    text, usage = await _call_anthropic(model, persona["system_prompt"], prompt, key_idx)
                else:
                    text, usage = await _call_google(model, persona["system_prompt"], prompt, key_idx)
                latency_ms = int((time.time() - call_start) * 1000)
                token_usage = usage

                parse_result = _robust_json_parse(text)
                params = parse_result["parsed"]
                parse_status = parse_result["status"]

                if parse_status == "repaired":
                    errors.append({
                        "agent": agent_key, "provider": provider, "model": model,
                        "stage": "json_parse",
                        "message": "Malformed JSON repaired via regex/bracket extraction",
                        "severity": "warning"
                    })
                elif parse_status == "failed":
                    errors.append({
                        "agent": agent_key, "provider": provider, "model": model,
                        "stage": "json_parse",
                        "message": "Complete JSON parse failure. Defaulting values.",
                        "severity": "error"
                    })

                clamped = {}
                valid_count = 0
                for key, schema in PARAMETER_SCHEMA.items():
                    if key in params:
                        value = params[key]
                        try:
                            val_f = float(value)
                            if math.isnan(val_f) or math.isinf(val_f):
                                val_f = schema["default"]
                            else:
                                valid_count += 1
                        except (ValueError, TypeError):
                            val_f = schema["default"]
                        clamped[key] = max(schema["min"], min(schema["max"], val_f))
                    else:
                        clamped[key] = schema["default"]

                is_fallback = attempt > 0 or key_idx > 0
                if is_fallback:
                    msg = f"Agent {agent_key}: succeeded with key[{key_idx}]/{model}"
                    logger.warning(msg)
                    errors.append({
                        "agent": agent_key, "provider": provider, "model": model,
                        "stage": "fallback", "message": msg, "severity": "warning"
                    })

                valid_ratio = valid_count / len(PARAMETER_SCHEMA) if PARAMETER_SCHEMA else 1.0
                raw_confidence = float(params.get("confidence", 0.7))

                return {
                    "agent_name": agent_key,
                    "provider": provider,
                    "model": model,
                    "is_fallback": is_fallback,
                    "latency_ms": latency_ms,
                    "parse_status": parse_status,
                    "raw_response_size": len(text),
                    "confidence": min(1.0, max(0.0, raw_confidence)),
                    "valid_param_ratio": valid_ratio,
                    **clamped,
                    "rationale": params.get("rationale", f"Agent {agent_key} analysis"),
                    "section_overrides": params.get("section_overrides", []),
                    "errors": errors,
                    "token_usage": token_usage
                }

            except Exception as e:
                msg = str(e)
                is_last = (key_idx == key_pool_size - 1) and (attempt > 0 or fallback_model is None)
                severity = "error" if is_last else "warning"
                errors.append({
                    "agent": agent_key, "provider": provider, "model": model,
                    "stage": "api_call", "message": f"key[{key_idx}] {msg}",
                    "severity": severity
                })
                logger.warning(f"Agent {agent_key} key[{key_idx}]/{model} failed: {e}")

    default_op = _default_opinion(agent_key)
    default_op["errors"] = errors
    default_op["token_usage"] = token_usage
    return default_op


async def _call_openai(model: str, system_prompt: str, user_prompt: str, key_index: int = 0) -> tuple[str, dict]:
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
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        } if getattr(response, 'usage', None) else {}
        return response.choices[0].message.content, usage

    return await asyncio.to_thread(_sync_call)


async def _call_anthropic(model: str, system_prompt: str, user_prompt: str, key_index: int = 0) -> tuple[str, dict]:
    """Call Anthropic API and return raw JSON text, along with token usage."""
    client = _get_anthropic_client(key_index)

    def _sync_call():
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt + "\n\nRespond with a JSON object only."},
            ],
            temperature=0.3,
        )
        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens
        } if getattr(response, 'usage', None) else {}
        return response.content[0].text, usage

    return await asyncio.to_thread(_sync_call)


async def _call_google(model: str, system_prompt: str, user_prompt: str, key_index: int = 0) -> tuple[str, dict]:
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
        um = getattr(response, 'usage_metadata', None)
        if um:
            usage = {
                "prompt_tokens": getattr(um, 'prompt_token_count', 0),
                "completion_tokens": getattr(um, 'candidates_token_count', 0),
                "total_tokens": getattr(um, 'total_token_count', 0)
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
        "confidence": 0.3,
        "valid_param_ratio": 0.25,
        **defaults,
        "rationale": f"Default safe parameters (agent {agent_key} did not respond)",
        "section_overrides": [],
    }



def _weighted_median_merge(opinions: Sequence[dict]) -> dict:
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
            parse_status = op.get("parse_status", "ok")
            
            parse_multiplier = 1.0
            if parse_status == "repaired": parse_multiplier = 0.8
            elif parse_status == "failed": parse_multiplier = 0.1
            
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

    return adopted


def _calculate_deliberation_score(opinions: Sequence[dict]) -> dict:
    """Decompose agreement into categories for experimental logs."""
    if len(opinions) < 2:
        return {
            "global": 1.0, "dynamics": 1.0, "tone": 1.0, "stereo": 1.0, "saturation": 1.0
        }

    categories = {
        "dynamics": ["comp_threshold_db", "comp_ratio", "comp_attack_sec", "comp_release_sec", "limiter_ceil_db", "input_gain_db"],
        "tone": ["eq_low_shelf_gain_db", "eq_low_mid_gain_db", "eq_high_mid_gain_db", "eq_high_shelf_gain_db", "dyn_eq_enabled"],
        "stereo": ["ms_side_high_gain_db", "ms_mid_low_gain_db", "stereo_low_mono", "stereo_high_wide", "stereo_width"],
        "saturation": ["transformer_saturation", "transformer_mix", "triode_drive", "triode_bias", "triode_mix", "tape_saturation", "tape_mix", "parallel_wet"]
    }
    
    agreements = {}
    total_agreements = []
    
    for cat_name, keys in categories.items():
        cat_agreements = []
        for key in keys:
            if key not in PARAMETER_SCHEMA: continue
            values = [op.get(key, 0) for op in opinions]
            schema = PARAMETER_SCHEMA[key]
            param_range = schema["max"] - schema["min"]
            if param_range == 0: continue
            
            spread = max(values) - min(values)
            agreement = max(0.0, 1.0 - (spread / param_range))
            cat_agreements.append(agreement)
            total_agreements.append(agreement)
            
        agreements[cat_name] = round(sum(cat_agreements) / len(cat_agreements), 3) if cat_agreements else 0.5
        
    agreements["global"] = round(sum(total_agreements) / len(total_agreements), 3) if total_agreements else 0.5
    return agreements


def _get_12_agents_personas() -> dict:
    """"12 Specialist Agent" Configuration - High resolution parameter negotiation"""
    themes = [
        ("High-Frequency Specialist", "Focus purely on high-frequency transient enhancement, airiness, and high-shelf EQ management."),
        ("Sub-Bass Specialist", "Focus strictly on sub-bass stability. Prevent phase issues below 120Hz. Advocate for low-end monoization."),
        ("Mid-Range Specialist", "Focus on the mid-range flow, stereo width in the body of the track, and vocal/lead continuity."),
        ("Harmonic Saturation Specialist", "Focus on tube distortion, punch, and clipping. Push triode drive and aggressive harmonic generation safely."),
        ("Acoustic Space Specialist", "Focus on acoustic space, reverb tails, and dynamic range preservation. Advocate for minimal compression ratios."),
        ("Transient Specialist", "Focus on transient attack times and True Peak limiting. Fast processing, precise compression attacks."),
        ("Warmth Specialist", "Focus on low-mid warmth and tape saturation to provide thickness and organic density."),
        ("Stereo Imaging Specialist", "Focus entirely on the stereo side channels, evaluating ethereal wideness and mid-side balance."),
        ("Loudness/Center Specialist", "Focus on integrated loudness and center channel authority. Dictate overall LUFS gain unconditionally."),
        ("Dynamic EQ Specialist", "Focus on surgical dynamic EQ and harshness removal, specifically in the 3kHz-5kHz range."),
        ("Parallel Processing Specialist", "Focus on parallel processing (parallel_wet). Recommend hidden compression and saturation without affecting the dry transients."),
        ("Standards & Compliance Specialist", "Final arbiter of BS.1770-4 compliance. Verify target LUFS and True Peak limits.")
    ]
    
    # Each provider has primary + same-provider fallback (D-09 fix)
    providers = [
        ("openai", "gpt-5.4", "gpt-5.2"),
        ("anthropic", "claude-opus-4-6", "claude-sonnet-4-6"),
        ("google", "gemini-3.1-pro-preview", "gemini-3-flash-preview")
    ]
    
    personas = {}
    for i, (name, prompt) in enumerate(themes):
        prov, mod, fallback = providers[i % 3]
        personas[f"agent_{i+1}"] = {
            "name": name,
            "provider": prov,
            "model": mod,
            "fallback_model": fallback,
            "system_prompt": f"You are the {name}. {prompt} Propose mastering parameters based entirely on your domain while respecting physical signal limits."
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
            "system_prompt": "You are the master of the Attack phase. You analyze the first 0-15ms of every percussive hit. You demand precise compressor attacks and high True Peak safety."
        },
        "sustain_analyst": {
            "name": "Sustain Analyst",
            "provider": "google",
            "model": default_model,
            "fallback_model": "gemini-3-flash-preview",
            "system_prompt": "You govern the body of the sound (15ms-200ms). You demand parallel saturation, Triode drive, and Tape warmth to thicken the sustain."
        },
        "release_analyst": {
            "name": "Release Analyst",
            "provider": "google",
            "model": default_model,
            "fallback_model": "gemini-3-flash-preview",
            "system_prompt": "You only care about how signals fade. You dictate the breathing of the mix. You demand correct release times on the compressor to match the BPM groove."
        },
        "macro_dynamic_analyst": {
            "name": "MacroDynamics Analyst",
            "provider": "google",
            "model": default_model,
            "fallback_model": "gemini-3-flash-preview",
            "system_prompt": "You look at the song globally. You manage long-term Integrated LUFS, target dynamic EQ, and ensure the song dynamically grows across sections."
        }
    }

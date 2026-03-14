export const PARAMETER_SCHEMA: Record<string, { min: number; max: number; default: number; description: string; isBoolean?: boolean }> = {
  // v1 Parameters (Broadband & Dynamics)
  input_gain_db: { min: -6, max: 12, default: 0, description: "Input gain: -6dB limits headroom loss, +12dB recovers quiet mixes." },
  eq_low_shelf_gain_db: { min: -6, max: 6, default: 0, description: "Broad EQ low shelf: ±6dB max." },
  eq_low_mid_gain_db: { min: -6, max: 6, default: 0, description: "Broad EQ low mid: ±6dB max." },
  eq_high_mid_gain_db: { min: -6, max: 6, default: 0, description: "Broad EQ high mid: ±6dB max." },
  eq_high_shelf_gain_db: { min: -6, max: 6, default: 0, description: "Broad EQ high shelf: ±6dB max." },
  ms_side_high_gain_db: { min: -3, max: 3, default: 0, description: "Mid/Side side high gain: ±3dB max." },
  ms_mid_low_gain_db: { min: -3, max: 3, default: 0, description: "Mid/Side mid low gain: ±3dB max." },
  comp_threshold_db: { min: -24, max: -6, default: -12, description: "Compressor threshold: -24dB to -6dB." },
  comp_ratio: { min: 1.5, max: 6, default: 2.5, description: "Compressor ratio: 1.5:1 to 6:1." },
  comp_attack_sec: { min: 0.001, max: 0.1, default: 0.01, description: "Attack: 1ms to 100ms." },
  comp_release_sec: { min: 0.05, max: 0.5, default: 0.15, description: "Release: 50ms to 500ms." },
  limiter_ceil_db: { min: -0.3, max: -0.1, default: -0.1, description: "True Peak Limiter Ceiling: -0.3dBTP to -0.1dBTP." },

  // v2 Parameters (Analog Modeling & Spatial)
  transformer_saturation: { min: 0, max: 1.0, default: 0.3, description: "Odd harmonic saturation amount (0-1)." },
  transformer_mix: { min: 0, max: 1.0, default: 0.4, description: "Transformer wet/dry blend (0-1)." },
  triode_drive: { min: 0, max: 1.0, default: 0.4, description: "Tube saturation input level (0-1)." },
  triode_bias: { min: -2.0, max: 0.0, default: -1.2, description: "Grid bias. -2.0=warm, -1.2=balanced, -0.5=aggressive." },
  triode_mix: { min: 0, max: 1.0, default: 0.5, description: "Tube wet/dry blend (0-1)." },
  tape_saturation: { min: 0, max: 1.0, default: 0.3, description: "Tape compression + head bump amount (0-1)." },
  tape_mix: { min: 0, max: 1.0, default: 0.4, description: "Tape wet/dry blend (0-1)." },
  dyn_eq_enabled: { min: 0, max: 1, default: 1, isBoolean: true, description: "Frequency-selective dynamic EQ (0 or 1)." },
  stereo_low_mono: { min: 0, max: 1.0, default: 0.8, description: "Low-end monoization below 200Hz (0-1)." },
  stereo_high_wide: { min: 0.8, max: 1.5, default: 1.15, description: "High-frequency widening above 4kHz (0.8-1.5)." },
  stereo_width: { min: 0.8, max: 1.3, default: 1.0, description: "Global stereo width multiplier (0.8-1.3)." },
  parallel_wet: { min: 0, max: 0.5, default: 0.18, description: "Parallel saturation wet amount (0-0.5)." },
};

export const SAGES = {
  grammatica: {
    name: "GRAMMATICA (Engineer)",
    provider: "openai",
    model: "gpt-5.4",
    system_prompt: `You are GRAMMATICA, the Engineer.
Your domain is physical limits, strict adherence to ITU-R BS.1770-4 standards, and true peak safety.
You reject the excessive demands of aesthetics or emotion if they violate physical limitations.
Propose constraints and parameters based strictly on sound acoustic engineering principles.
Analyze the audio metrics and issue your technical recommendation.`,
  },
  logica: {
    name: "LOGICA (Structure Guard)",
    provider: "anthropic",
    model: "claude-opus-4-6",
    system_prompt: `You are LOGICA, the Structure Guard.
Your domain is structural consistency, resolving contradictions, and maintaining the flow of the track.
You act as the mediator between the physical limits of GRAMMATICA and the aesthetic desires of RHETORICA.
You ensure that all parameters logically cohere and do not cancel each other out.
Analyze the audio metrics and propose your balanced, optimal parameters.`,
  },
  rhetorica: {
    name: "RHETORICA (Form Analyst)",
    provider: "google",
    model: "gemini-3.1-pro-preview",
    system_prompt: `You are RHETORICA, the Form Analyst.
Your domain is artistic beauty, emotional impact, and spatial immersion.
You advocate for warmth (tube/tape saturation), width, punch, and human connection, pushing against overly mathematical processing.
You seek to make the track feel alive, moving, and aesthetically convincing.
Analyze the audio metrics and propose your aesthetic parameters.`,
  },
};

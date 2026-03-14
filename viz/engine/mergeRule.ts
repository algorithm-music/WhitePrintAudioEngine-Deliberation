import { PARAMETER_SCHEMA } from '../domain/audioSchema';
import { Proposal } from '../domain/types';

export function weightedMedianMerge(opinions: Proposal[]): Record<string, number> {
  const adopted: Record<string, number> = {};
  if (!opinions || opinions.length === 0) return adopted;

  for (const [key, schema] of Object.entries(PARAMETER_SCHEMA)) {
    const min_v = schema.min;
    const max_v = schema.max;
    const default_v = schema.default;

    const values = opinions.map(op => {
      const val = op.params[key];
      return typeof val === 'number' ? val : default_v;
    });
    const weights = opinions.map(op => op.confidence || 0.5);
    const total_weight = weights.reduce((a, b) => a + b, 0) + 1e-6;

    const is_boolean = schema.isBoolean || (min_v === 0 && max_v === 1 && Number.isInteger(default_v));

    if (is_boolean) {
      // Majority vote based on weights
      let votes_for = 0;
      for (let i = 0; i < values.length; i++) {
        if (values[i] >= 0.5) {
          votes_for += weights[i];
        }
      }
      adopted[key] = votes_for >= total_weight / 2 ? 1 : 0;
      continue;
    }

    // Weighted median
    const pairs = values.map((val, i) => ({ val, w: weights[i] })).sort((a, b) => a.val - b.val);
    let cumulative = 0.0;
    let median_value = pairs[pairs.length - 1].val; // fallback

    for (const pair of pairs) {
      cumulative += pair.w;
      if (cumulative >= total_weight / 2) {
        median_value = pair.val;
        break;
      }
    }

    // Clamp to bounds
    const clamped = Math.max(min_v, Math.min(max_v, median_value));
    adopted[key] = Number(clamped.toFixed(4));
  }

  return adopted;
}

export function calculateDeliberationScore(opinions: Proposal[]): number {
  if (opinions.length < 2) return 1.0;

  const agreements: number[] = [];
  for (const [key, schema] of Object.entries(PARAMETER_SCHEMA)) {
    const values = opinions.map(op => {
      const val = op.params[key];
      return typeof val === 'number' ? val : schema.default;
    });
    
    const param_range = schema.max - schema.min;
    if (param_range === 0) continue;

    const max_val = Math.max(...values);
    const min_val = Math.min(...values);
    const spread = max_val - min_val;
    const agreement = 1.0 - (spread / param_range);
    agreements.push(agreement);
  }

  if (agreements.length === 0) return 0.5;
  const sum = agreements.reduce((a, b) => a + b, 0);
  return sum / agreements.length;
}

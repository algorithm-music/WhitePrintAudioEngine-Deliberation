import { ObjectiveScore, ParameterVector, WorldState } from './types';

export type ObjectiveFunction = {
  technicalScore: (x: ParameterVector, world: WorldState) => number;
  structuralScore: (x: ParameterVector, world: WorldState) => number;
  aestheticScore: (x: ParameterVector, world: WorldState) => number;
  penaltyScore: (x: ParameterVector, world: WorldState) => number;
};

// Example domain: Product Strategy
// Parameters:
// - budget_marketing (0-100)
// - budget_rd (0-100)
// - budget_operations (0-100)
// - risk_level (0-1)
// - timeline_weeks (4-52)

export const defaultObjective: ObjectiveFunction = {
  technicalScore: (x, world) => {
    // Technical score favors R&D and lower risk
    const rd = Number(x.budget_rd || 0);
    const risk = Number(x.risk_level || 0.5);
    return (rd * 0.6) + ((1 - risk) * 40);
  },
  structuralScore: (x, world) => {
    // Structural score favors operations and balanced timeline
    const ops = Number(x.budget_operations || 0);
    const timeline = Number(x.timeline_weeks || 24);
    const timelineScore = timeline >= 12 && timeline <= 36 ? 100 : 50;
    return (ops * 0.5) + (timelineScore * 0.5);
  },
  aestheticScore: (x, world) => {
    // Aesthetic (market appeal) favors marketing and higher risk/innovation
    const mkt = Number(x.budget_marketing || 0);
    const risk = Number(x.risk_level || 0.5);
    return (mkt * 0.6) + (risk * 40);
  },
  penaltyScore: (x, world) => {
    let penalty = 0;
    const mkt = Number(x.budget_marketing || 0);
    const rd = Number(x.budget_rd || 0);
    const ops = Number(x.budget_operations || 0);
    
    // Penalty if budgets don't sum to 100
    const sum = mkt + rd + ops;
    if (Math.abs(sum - 100) > 1) {
      penalty += Math.abs(sum - 100) * 2;
    }

    // Penalty if timeline is too short for high R&D
    const timeline = Number(x.timeline_weeks || 24);
    if (rd > 40 && timeline < 12) {
      penalty += 30;
    }

    return penalty;
  }
};

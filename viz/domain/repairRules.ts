import { ParameterVector, WorldState } from './types';

export type RepairRule = {
  id: string;
  condition: (x: ParameterVector, world: WorldState) => boolean;
  repair: (x: ParameterVector, world: WorldState) => ParameterVector;
};

export const repairRules: RepairRule[] = [
  {
    id: 'repair_budget_sum',
    condition: (x, world) => {
      const mkt = Number(x.budget_marketing || 0);
      const rd = Number(x.budget_rd || 0);
      const ops = Number(x.budget_operations || 0);
      return Math.abs(mkt + rd + ops - 100) > 1;
    },
    repair: (x, world) => {
      const mkt = Number(x.budget_marketing || 0);
      const rd = Number(x.budget_rd || 0);
      const ops = Number(x.budget_operations || 0);
      const sum = mkt + rd + ops;
      
      if (sum === 0) {
        return { ...x, budget_marketing: 33, budget_rd: 34, budget_operations: 33 };
      }

      return {
        ...x,
        budget_marketing: Math.round((mkt / sum) * 100),
        budget_rd: Math.round((rd / sum) * 100),
        budget_operations: Math.round((ops / sum) * 100)
      };
    }
  },
  {
    id: 'repair_risk_bounds',
    condition: (x, world) => {
      const risk = Number(x.risk_level || 0.5);
      return risk < 0 || risk > 1;
    },
    repair: (x, world) => {
      const risk = Number(x.risk_level || 0.5);
      return { ...x, risk_level: Math.max(0, Math.min(1, risk)) };
    }
  },
  {
    id: 'repair_timeline_bounds',
    condition: (x, world) => {
      const timeline = Number(x.timeline_weeks || 24);
      return timeline < 4 || timeline > 52;
    },
    repair: (x, world) => {
      const timeline = Number(x.timeline_weeks || 24);
      return { ...x, timeline_weeks: Math.max(4, Math.min(52, timeline)) };
    }
  }
];

export function applyRepairs(params: ParameterVector, world: WorldState): ParameterVector {
  let repaired = { ...params };
  for (const rule of repairRules) {
    if (rule.condition(repaired, world)) {
      repaired = rule.repair(repaired, world);
    }
  }
  return repaired;
}

import { AgentUtility, ObjectiveScore, ParameterVector, WorldState } from './types';
import { defaultObjective } from './objective';

export function computeObjectiveScore(
  params: ParameterVector,
  world: WorldState,
  utility?: AgentUtility
): ObjectiveScore {
  const technical = defaultObjective.technicalScore(params, world);
  const structural = defaultObjective.structuralScore(params, world);
  const aesthetic = defaultObjective.aestheticScore(params, world);
  const penalty = defaultObjective.penaltyScore(params, world);

  // If calculating for a specific agent, use their weights
  // Otherwise, use a balanced global weight
  const weights = utility?.weights || {
    technical: 0.33,
    structural: 0.33,
    aesthetic: 0.33,
    penalty: 1.0
  };

  const total = 
    (weights.technical * technical) +
    (weights.structural * structural) +
    (weights.aesthetic * aesthetic) -
    (weights.penalty * penalty);

  return {
    technical,
    structural,
    aesthetic,
    total: Math.max(0, total) // Prevent negative total scores
  };
}

import { ConsensusState, IterationRecord, ParameterVector } from '../domain/types';

export function hasConverged(state: ConsensusState): boolean {
  if (state.history.length < 2) return false;

  const current = state.history[state.history.length - 1];
  const previous = state.history[state.history.length - 2];

  if (!current.selected || !previous.selected) return false;

  // 1. Check parameter distance
  const distance = calculateDistance(current.selected.params, previous.selected.params);
  if (distance < 0.05) return true;

  // 2. Check objective improvement
  const currentScore = current.score?.total || 0;
  const previousScore = previous.score?.total || 0;
  if (currentScore - previousScore < 0.01 && currentScore > 0) return true;

  // 3. Max iterations
  if (state.world.iteration >= 5) return true;

  return false;
}

function calculateDistance(p1: ParameterVector, p2: ParameterVector): number {
  let sum = 0;
  let count = 0;
  for (const key in p1) {
    if (typeof p1[key] === 'number' && typeof p2[key] === 'number') {
      const diff = (p1[key] as number) - (p2[key] as number);
      sum += diff * diff;
      count++;
    }
  }
  return count > 0 ? Math.sqrt(sum / count) : 0;
}

import { ConsensusState, IterationRecord, Proposal, WorldState } from '../domain/types';
import { computeObjectiveScore } from '../domain/scoring';
import { validateConstraints } from '../domain/constraints';
import { generateProposals } from './proposalGenerator';
import { requestBestResponses } from './bestResponse';
import { weightedMedianMerge, calculateDeliberationScore } from './mergeRule';

export async function runConsensus(state: ConsensusState, onUpdate: (state: ConsensusState) => void): Promise<ConsensusState> {
  // Deep copy to prevent React state mutation bugs
  let currentState: ConsensusState = JSON.parse(JSON.stringify(state));

  while (!currentState.world.converged && currentState.world.iteration < 3) {
    currentState.world.iteration++;
    onUpdate(JSON.parse(JSON.stringify(currentState)));

    let newProposals: Proposal[] = [];

    if (currentState.world.iteration === 1) {
      // Iteration 1: Independent Assessment
      newProposals = await generateProposals(currentState);
    } else {
      // Iteration 2 & 3: Critique & Revise against the current selected proposal
      const topCandidate = currentState.selectedProposal!;
      newProposals = await requestBestResponses(topCandidate, currentState);
    }

    // Score and Validate
    const scoredProposals = newProposals.map(p => {
      const violations = validateConstraints(p.params, currentState.world);
      const score = computeObjectiveScore(p.params, currentState.world);
      return { ...p, violations, predictedScore: score };
    });

    // Deterministic Weighted Median Merge
    const mergedParams = weightedMedianMerge(scoredProposals);
    
    // Score the merged result
    const mergedViolations = validateConstraints(mergedParams, currentState.world);
    const mergedScore = computeObjectiveScore(mergedParams, currentState.world);

    // Create a synthetic proposal for the merged result
    const finalSelected: Proposal = {
      id: `merged-result-iter-${currentState.world.iteration}`,
      agentId: 'system',
      params: mergedParams,
      rationale: `Adopted via deterministic weighted median merge of iteration ${currentState.world.iteration} proposals.`,
      confidence: calculateDeliberationScore(scoredProposals),
      predictedScore: mergedScore,
      violations: mergedViolations
    };

    // Update State
    const record: IterationRecord = {
      iteration: currentState.world.iteration,
      proposals: scoredProposals,
      selected: finalSelected,
      score: mergedScore,
      violations: mergedViolations || []
    };

    currentState.history.push(record);
    currentState.world.currentParams = finalSelected.params;
    currentState.proposalPool.push(...scoredProposals);
    currentState.selectedProposal = finalSelected;

    // Convergence Check
    if (finalSelected.confidence >= 0.85 || currentState.world.iteration >= 3) {
      currentState.world.converged = true;
    }

    onUpdate(JSON.parse(JSON.stringify(currentState)));
  }

  return currentState;
}

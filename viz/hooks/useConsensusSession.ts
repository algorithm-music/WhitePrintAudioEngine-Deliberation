import { useState } from 'react';
import { ConsensusState, WorldState, AgentState } from '../domain/types';
import { runConsensus } from '../engine/consensusRunner';
import { PARAMETER_SCHEMA, SAGES } from '../domain/audioSchema';
import { runFullScan } from '../engine/fullScan';

export function useConsensusSession() {
  const [state, setState] = useState<ConsensusState | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isScanning, setIsScanning] = useState(false);

  const run = async (query: string) => {
    setIsRunning(true);
    setIsScanning(true);

    try {
      // 1. Full Scan (Gemini 1.5 Pro) - The only model that "listens" to the whole track
      const analysisData = await runFullScan(query);
      setIsScanning(false);

      const defaultParams: Record<string, number> = {};
      for (const [key, schema] of Object.entries(PARAMETER_SCHEMA)) {
        defaultParams[key] = schema.default;
      }

      const initialWorld: WorldState = {
        query,
        analysisData,
        extractedRequirements: [],
        currentParams: defaultParams,
        constraints: ['ITU-R BS.1770-4 compliance', 'True Peak <= -0.1 dBTP'],
        objectiveTargets: { technical: 80, structural: 80, aesthetic: 80 },
        iteration: 0,
        converged: false
      };

      const agents: AgentState[] = [
        {
          id: 'grammatica',
          role: 'engineer',
          model: 'gemini-3-flash-preview',
          phase: 'idle',
          belief: { assumptions: ['Physical limits are absolute'], risks: ['Clipping', 'Phase cancellation'], priorities: ['Safety', 'Compliance'] },
          goal: { maximize: ['technicalScore'], minimize: ['true_peak'], hardConstraints: ['limiter_ceil_db <= -0.1'] },
          utility: { weights: { technical: 0.8, structural: 0.1, aesthetic: 0.1, penalty: 1.0 } },
          memory: { pastProposals: [], pastScores: [], observations: [] }
        },
        {
          id: 'logica',
          role: 'planner',
          model: 'gemini-3-flash-preview',
          phase: 'idle',
          belief: { assumptions: ['Structure dictates flow'], risks: ['Contradictory parameters'], priorities: ['Consistency'] },
          goal: { maximize: ['structuralScore'], minimize: ['phase_issues'], hardConstraints: ['stereo_width <= 1.3'] },
          utility: { weights: { technical: 0.3, structural: 0.6, aesthetic: 0.1, penalty: 1.0 } },
          memory: { pastProposals: [], pastScores: [], observations: [] }
        },
        {
          id: 'rhetorica',
          role: 'creative',
          model: 'gemini-3-flash-preview',
          phase: 'idle',
          belief: { assumptions: ['Emotion drives impact'], risks: ['Sterile sound'], priorities: ['Warmth', 'Width', 'Punch'] },
          goal: { maximize: ['aestheticScore'], minimize: ['harshness'], hardConstraints: ['must_feel_alive'] },
          utility: { weights: { technical: 0.1, structural: 0.2, aesthetic: 0.7, penalty: 1.0 } },
          memory: { pastProposals: [], pastScores: [], observations: [] }
        }
      ];

      const initialState: ConsensusState = {
        world: initialWorld,
        agents,
        proposalPool: [],
        history: []
      };

      setState(initialState);

      await runConsensus(initialState, (newState) => {
        setState({ ...newState });
      });
    } catch (error) {
      console.error('Consensus failed:', error);
      setIsScanning(false);
    } finally {
      setIsRunning(false);
    }
  };

  return { state, run, isRunning, isScanning };
}

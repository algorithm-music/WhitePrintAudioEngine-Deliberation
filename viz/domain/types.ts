import { z } from 'zod';

export type ParameterVector = Record<string, number | boolean | string>;

export type ConstraintViolation = {
  id: string;
  severity: 'low' | 'medium' | 'high' | 'fatal';
  message: string;
  affectedParams: string[];
};

export type ObjectiveScore = {
  technical: number;
  structural: number;
  aesthetic: number;
  total: number;
};

export type AgentBelief = {
  assumptions: string[];
  risks: string[];
  priorities: string[];
};

export type AgentGoal = {
  maximize: string[];
  minimize: string[];
  hardConstraints: string[];
};

export type AgentUtility = {
  weights: Record<string, number>;
};

export type AgentPhase =
  | 'idle'
  | 'observing'
  | 'proposing'
  | 'critiquing'
  | 'revising'
  | 'accepting'
  | 'converged';

export type AgentState = {
  id: string;
  role: 'planner' | 'engineer' | 'critic' | 'creative' | 'mediator';
  model: string;
  phase: AgentPhase;
  belief: AgentBelief;
  goal: AgentGoal;
  utility: AgentUtility;
  memory: {
    pastProposals: ParameterVector[];
    pastScores: ObjectiveScore[];
    observations: string[];
  };
  latestProposal?: ParameterVector;
};

export type WorldState = {
  query: string;
  analysisData?: any;
  extractedRequirements: string[];
  currentParams: ParameterVector;
  constraints: string[];
  objectiveTargets: Record<string, number>;
  iteration: number;
  converged: boolean;
};

export type Proposal = {
  id: string;
  agentId: string;
  params: ParameterVector;
  rationale: string;
  confidence: number;
  predictedScore?: ObjectiveScore;
  violations?: ConstraintViolation[];
  critiques?: string[];
};

export type IterationRecord = {
  iteration: number;
  proposals: Proposal[];
  selected?: Proposal;
  score?: ObjectiveScore;
  violations: ConstraintViolation[];
};

export type ConsensusState = {
  world: WorldState;
  agents: AgentState[];
  proposalPool: Proposal[];
  selectedProposal?: Proposal;
  history: IterationRecord[];
};

export const ProposalSchema = z.object({
  params: z.record(z.string(), z.union([z.number(), z.boolean(), z.string()])),
  rationale: z.string(),
  confidence: z.number().min(0).max(1),
  critiques: z.array(z.string()).optional(),
});

export type ProposalPayload = z.infer<typeof ProposalSchema>;

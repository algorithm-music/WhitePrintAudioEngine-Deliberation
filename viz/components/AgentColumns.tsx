import { ConsensusState, AgentState, Proposal } from '../domain/types';

export function AgentColumns({ state }: { state: ConsensusState }) {
  if (state.history.length === 0) return null;

  const currentIteration = state.history[state.history.length - 1];
  const proposals = currentIteration.proposals;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {state.agents.map(agent => {
        // Find the latest proposal for this agent (revised if available, else initial)
        const agentProposals = proposals.filter(p => p.agentId === agent.id);
        const latestProposal = agentProposals[agentProposals.length - 1];
        
        return <AgentColumn key={agent.id} agent={agent} proposal={latestProposal} />;
      })}
    </div>
  );
}

function AgentColumn({ agent, proposal }: { agent: AgentState, proposal?: Proposal }) {
  const colorMap: Record<string, string> = {
    engineer: 'border-amber-500/20 bg-amber-500/5 text-amber-400',
    planner: 'border-blue-500/20 bg-blue-500/5 text-blue-400',
    creative: 'border-rose-500/20 bg-rose-500/5 text-rose-400'
  };

  const colorClass = colorMap[agent.role] || 'border-zinc-500/20 bg-zinc-500/5 text-zinc-400';

  return (
    <div className={`flex flex-col rounded-xl border ${colorClass} overflow-hidden h-full min-h-[300px]`}>
      <div className="p-4 border-b border-zinc-800/50 bg-zinc-950/50">
        <h3 className={`font-mono text-xs tracking-widest font-bold uppercase mb-1`}>{agent.id}</h3>
        <p className="text-xs text-zinc-400 font-serif line-clamp-2">{agent.role}</p>
      </div>
      <div className="p-5 flex-1 overflow-y-auto bg-zinc-900/20">
        {proposal ? (
          <div className="text-sm text-zinc-300 leading-relaxed flex flex-col gap-4">
            <div>
              <h4 className="font-bold text-zinc-500 text-xs mb-2">Rationale</h4>
              <p>{proposal.rationale}</p>
            </div>
            <div>
              <h4 className="font-bold text-zinc-500 text-xs mb-2">Proposed Parameters</h4>
              <pre className="text-xs font-mono text-zinc-400 bg-zinc-950 p-2 rounded">
                {JSON.stringify(proposal.params, null, 2)}
              </pre>
            </div>
            {proposal.critiques && proposal.critiques.length > 0 && (
              <div>
                <h4 className="font-bold text-zinc-500 text-xs mb-2">Critiques</h4>
                <ul className="list-disc pl-4 text-xs text-zinc-400">
                  {proposal.critiques.map((c, i) => <li key={i}>{c}</li>)}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-center h-full opacity-50">
            <span className="text-xs font-mono">Waiting for proposal...</span>
          </div>
        )}
      </div>
    </div>
  );
}

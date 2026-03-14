import { ConsensusState } from '../domain/types';

export function ProposalPool({ state }: { state: ConsensusState }) {
  if (state.history.length === 0) return null;

  const currentIteration = state.history[state.history.length - 1];
  
  // Include the selected proposal in the list if it's not already there
  const allProposals = [...currentIteration.proposals];
  if (currentIteration.selected && !allProposals.find(p => p.id === currentIteration.selected!.id)) {
    allProposals.push(currentIteration.selected);
  }

  return (
    <div className="p-6 bg-zinc-900 rounded-xl border border-zinc-800">
      <h2 className="text-xl font-serif text-zinc-100 mb-4">Proposal Evaluation Pool</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-zinc-400">
          <thead className="text-xs text-zinc-500 uppercase bg-zinc-950 border-b border-zinc-800">
            <tr>
              <th className="px-4 py-3 font-mono">Agent</th>
              <th className="px-4 py-3 font-mono">Type</th>
              <th className="px-4 py-3 font-mono">Technical</th>
              <th className="px-4 py-3 font-mono">Structural</th>
              <th className="px-4 py-3 font-mono">Aesthetic</th>
              <th className="px-4 py-3 font-mono text-emerald-500">Total Score</th>
              <th className="px-4 py-3 font-mono text-red-400">Violations</th>
              <th className="px-4 py-3 font-mono">Status</th>
            </tr>
          </thead>
          <tbody>
            {allProposals.map((proposal, i) => {
              const isSelected = currentIteration.selected?.id === proposal.id;
              const isRevised = proposal.id.includes('revised');
              const isSystem = proposal.agentId === 'system';
              
              let typeLabel = 'Initial';
              if (isRevised) typeLabel = 'Revised';
              if (isSystem) typeLabel = 'Merged';

              return (
                <tr key={i} className={`border-b border-zinc-800/50 ${isSelected ? 'bg-emerald-950/20' : 'hover:bg-zinc-900/50'}`}>
                  <td className="px-4 py-3 font-bold text-zinc-300">{proposal.agentId}</td>
                  <td className="px-4 py-3 text-xs font-mono text-zinc-500">{typeLabel}</td>
                  <td className="px-4 py-3">{proposal.predictedScore?.technical.toFixed(1)}</td>
                  <td className="px-4 py-3">{proposal.predictedScore?.structural.toFixed(1)}</td>
                  <td className="px-4 py-3">{proposal.predictedScore?.aesthetic.toFixed(1)}</td>
                  <td className="px-4 py-3 font-bold text-emerald-500">{proposal.predictedScore?.total.toFixed(1)}</td>
                  <td className="px-4 py-3">
                    {proposal.violations && proposal.violations.length > 0 ? (
                      <span className="text-red-400">{proposal.violations.length}</span>
                    ) : (
                      <span className="text-emerald-500">0</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {isSelected ? (
                      <span className="px-2 py-1 bg-emerald-500/10 text-emerald-400 rounded text-xs font-bold uppercase">Selected</span>
                    ) : (
                      <span className="px-2 py-1 bg-zinc-800 text-zinc-500 rounded text-xs font-bold uppercase">Rejected</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

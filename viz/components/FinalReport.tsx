import { ConsensusState } from '../domain/types';

export function FinalReport({ state }: { state: ConsensusState }) {
  if (!state.world.converged) return null;

  return (
    <div className="p-8 bg-emerald-950/30 rounded-2xl border border-emerald-900/50 flex flex-col items-center justify-center text-center">
      <h2 className="text-3xl font-serif text-emerald-400 mb-4">Consensus Reached</h2>
      <p className="text-emerald-200/70 max-w-2xl mx-auto mb-8">
        The agents have successfully converged on a set of parameters that satisfy the constraints and maximize the objective functions.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 w-full max-w-4xl text-left">
        <div className="p-6 bg-zinc-950 rounded-xl border border-zinc-800">
          <h3 className="text-sm font-mono text-zinc-500 uppercase mb-4">Final Parameters</h3>
          <pre className="text-sm font-mono text-zinc-300 overflow-auto">
            {JSON.stringify(state.world.currentParams, null, 2)}
          </pre>
        </div>
        <div className="p-6 bg-zinc-950 rounded-xl border border-zinc-800">
          <h3 className="text-sm font-mono text-zinc-500 uppercase mb-4">Final Score</h3>
          <div className="flex flex-col gap-2">
            <div className="flex justify-between text-sm text-zinc-400">
              <span>Technical</span>
              <span className="font-mono text-amber-500">{state.selectedProposal?.predictedScore?.technical.toFixed(1)}</span>
            </div>
            <div className="flex justify-between text-sm text-zinc-400">
              <span>Structural</span>
              <span className="font-mono text-blue-500">{state.selectedProposal?.predictedScore?.structural.toFixed(1)}</span>
            </div>
            <div className="flex justify-between text-sm text-zinc-400">
              <span>Aesthetic</span>
              <span className="font-mono text-rose-500">{state.selectedProposal?.predictedScore?.aesthetic.toFixed(1)}</span>
            </div>
            <div className="h-px bg-zinc-800 my-2" />
            <div className="flex justify-between text-base font-bold text-zinc-200">
              <span>Total Score</span>
              <span className="font-mono text-emerald-500">{state.selectedProposal?.predictedScore?.total.toFixed(1)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

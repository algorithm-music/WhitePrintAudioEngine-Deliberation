import { ConsensusState } from '../domain/types';

export function ConsensusTimeline({ state }: { state: ConsensusState }) {
  if (state.history.length === 0) return null;

  return (
    <div className="p-6 bg-zinc-900 rounded-xl border border-zinc-800">
      <h2 className="text-xl font-serif text-zinc-100 mb-4">Consensus Timeline</h2>
      <div className="flex flex-col gap-4">
        {state.history.map((record, i) => (
          <div key={i} className="p-4 bg-zinc-950 rounded-lg border border-zinc-800">
            <h3 className="text-sm font-bold text-amber-500 mb-2">Iteration {record.iteration}</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <h4 className="text-xs font-mono text-zinc-500 uppercase mb-2">Selected Parameters</h4>
                <pre className="text-xs font-mono text-zinc-400 overflow-auto">
                  {JSON.stringify(record.selected?.params, null, 2)}
                </pre>
              </div>
              <div>
                <h4 className="text-xs font-mono text-zinc-500 uppercase mb-2">Violations</h4>
                {record.violations.length > 0 ? (
                  <ul className="list-disc pl-4 text-xs text-red-400">
                    {record.violations.map((v, j) => <li key={j}>{v.message}</li>)}
                  </ul>
                ) : (
                  <span className="text-xs text-emerald-500">No violations</span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

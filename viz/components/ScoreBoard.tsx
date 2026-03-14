import { ConsensusState } from '../domain/types';

export function ScoreBoard({ state }: { state: ConsensusState }) {
  if (!state.selectedProposal || !state.selectedProposal.predictedScore) return null;

  const score = state.selectedProposal.predictedScore;

  return (
    <div className="p-6 bg-zinc-900 rounded-xl border border-zinc-800">
      <h2 className="text-xl font-serif text-zinc-100 mb-4">Current Objective Score</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <ScoreCard label="Technical" value={score.technical} color="text-amber-500" />
        <ScoreCard label="Structural" value={score.structural} color="text-blue-500" />
        <ScoreCard label="Aesthetic" value={score.aesthetic} color="text-rose-500" />
        <ScoreCard label="Total" value={score.total} color="text-emerald-500" />
      </div>
    </div>
  );
}

function ScoreCard({ label, value, color }: { label: string, value: number, color: string }) {
  return (
    <div className="p-4 bg-zinc-950 rounded-lg border border-zinc-800 flex flex-col items-center justify-center">
      <span className="text-xs font-mono text-zinc-500 uppercase tracking-widest mb-2">{label}</span>
      <span className={`text-2xl font-bold ${color}`}>{value.toFixed(1)}</span>
    </div>
  );
}

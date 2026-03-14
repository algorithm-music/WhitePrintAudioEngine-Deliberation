'use client';

import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts';
import { ConsensusState } from '../domain/types';

export function RadarBalance({ state }: { state: ConsensusState }) {
  if (!state.selectedProposal || !state.selectedProposal.predictedScore) return null;

  const score = state.selectedProposal.predictedScore;

  const data = [
    { subject: 'Technical', A: score.technical, fullMark: 100 },
    { subject: 'Structural', A: score.structural, fullMark: 100 },
    { subject: 'Aesthetic', A: score.aesthetic, fullMark: 100 },
  ];

  return (
    <div className="p-6 bg-zinc-900 rounded-xl border border-zinc-800 flex flex-col items-center justify-center">
      <h2 className="text-xl font-serif text-zinc-100 mb-4 self-start">Objective Balance</h2>
      <div className="w-full h-64">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart cx="50%" cy="50%" outerRadius="80%" data={data}>
            <PolarGrid stroke="#3f3f46" />
            <PolarAngleAxis dataKey="subject" tick={{ fill: '#a1a1aa', fontSize: 12, fontFamily: 'monospace' }} />
            <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: '#52525b' }} />
            <Radar name="Score" dataKey="A" stroke="#10b981" fill="#10b981" fillOpacity={0.3} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

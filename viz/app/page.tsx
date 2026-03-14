'use client';

import { useConsensusSession } from '../hooks/useConsensusSession';
import { QueryPanel } from '../components/QueryPanel';
import { AgentColumns } from '../components/AgentColumns';
import { ConsensusTimeline } from '../components/ConsensusTimeline';
import { ScoreBoard } from '../components/ScoreBoard';
import { RadarBalance } from '../components/RadarBalance';
import { FinalReport } from '../components/FinalReport';
import { ProposalPool } from '../components/ProposalPool';
import { SkeletonResults } from '../components/SkeletonResults';
import { SquareTerminal } from 'lucide-react';

export default function BethlehemSystem() {
  const { state, isRunning, isScanning, run } = useConsensusSession();

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-300 font-sans flex flex-col p-4 md:p-8">
      <div className="max-w-7xl mx-auto w-full flex flex-col gap-8">
        <header className="flex items-center gap-3 mb-4">
          <SquareTerminal className="w-8 h-8 text-amber-500" />
          <div>
            <h1 className="font-serif text-3xl text-zinc-100 tracking-wide">The Bethlehem Equilibrium</h1>
            <p className="text-zinc-500 font-mono text-xs uppercase tracking-widest mt-1">Deterministic Optimization & Multi-Agent Negotiation</p>
          </div>
        </header>

        <QueryPanel onRun={run} isRunning={isRunning} isScanning={isScanning} />

        {(isRunning || isScanning) && (!state || state.history.length === 0) && (
          <SkeletonResults />
        )}

        {state && state.history.length > 0 && (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="lg:col-span-2">
                <ScoreBoard state={state} />
              </div>
              <div className="lg:col-span-1">
                <RadarBalance state={state} />
              </div>
            </div>

            <AgentColumns state={state} />
            <ProposalPool state={state} />
            <ConsensusTimeline state={state} />
            <FinalReport state={state} />
          </>
        )}
      </div>
    </main>
  );
}

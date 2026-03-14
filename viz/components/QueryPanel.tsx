import { useState } from 'react';

export function QueryPanel({ onRun, isRunning, isScanning }: { onRun: (query: string) => void, isRunning: boolean, isScanning: boolean }) {
  const [query, setQuery] = useState('Design a sustainable bridge connecting two major city districts.');

  return (
    <div className="p-6 bg-zinc-900 rounded-xl border border-zinc-800 flex flex-col gap-4">
      <h2 className="text-xl font-serif text-zinc-100">Problem Statement</h2>
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="w-full bg-zinc-950 text-zinc-300 p-4 rounded-lg border border-zinc-800 focus:outline-none focus:border-emerald-500/50 resize-none h-32"
        placeholder="Enter a problem statement..."
        disabled={isRunning}
      />
      <button
        onClick={() => onRun(query)}
        disabled={isRunning || !query.trim()}
        className="self-end px-6 py-3 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-lg transition-colors"
      >
        {isScanning ? 'Full Scan in Progress...' : isRunning ? 'Running Consensus...' : 'Run Consensus Engine'}
      </button>
    </div>
  );
}

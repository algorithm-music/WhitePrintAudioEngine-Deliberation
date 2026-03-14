export function SkeletonResults() {
  return (
    <div className="flex flex-col gap-8 w-full mt-4">
      {/* Top Row: ScoreBoard & RadarBalance */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 p-6 bg-zinc-900/40 rounded-xl border border-zinc-800/50 flex flex-col gap-4">
          <div className="h-6 w-1/3 bg-zinc-800/50 rounded animate-pulse"></div>
          <div className="grid grid-cols-3 gap-4 mt-2">
            <div className="h-24 bg-zinc-800/30 rounded-lg animate-pulse"></div>
            <div className="h-24 bg-zinc-800/30 rounded-lg animate-pulse"></div>
            <div className="h-24 bg-zinc-800/30 rounded-lg animate-pulse"></div>
          </div>
        </div>
        <div className="lg:col-span-1 p-6 bg-zinc-900/40 rounded-xl border border-zinc-800/50 flex flex-col gap-4 items-center justify-center">
          <div className="h-6 w-1/2 bg-zinc-800/50 rounded animate-pulse mb-4 self-start"></div>
          <div className="w-32 h-32 rounded-full bg-zinc-800/30 animate-pulse"></div>
        </div>
      </div>

      {/* Agent Columns */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="p-6 bg-zinc-900/40 rounded-xl border border-zinc-800/50 flex flex-col gap-4">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-full bg-zinc-800/50 animate-pulse"></div>
              <div className="h-5 w-24 bg-zinc-800/50 rounded animate-pulse"></div>
            </div>
            <div className="h-4 w-full bg-zinc-800/30 rounded animate-pulse"></div>
            <div className="h-4 w-5/6 bg-zinc-800/30 rounded animate-pulse"></div>
            <div className="h-4 w-4/6 bg-zinc-800/30 rounded animate-pulse"></div>
            <div className="mt-4 h-20 bg-zinc-800/20 rounded-lg animate-pulse"></div>
          </div>
        ))}
      </div>

      {/* Proposal Pool */}
      <div className="p-6 bg-zinc-900/40 rounded-xl border border-zinc-800/50 flex flex-col gap-4">
        <div className="h-6 w-1/4 bg-zinc-800/50 rounded animate-pulse"></div>
        <div className="h-12 w-full bg-zinc-800/30 rounded-lg animate-pulse"></div>
        <div className="h-12 w-full bg-zinc-800/30 rounded-lg animate-pulse"></div>
      </div>
    </div>
  );
}

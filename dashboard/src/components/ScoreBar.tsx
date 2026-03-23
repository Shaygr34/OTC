interface ScoreBarProps {
  score: number | null;
  max?: number;
  completeness?: number | null;
}

export default function ScoreBar({ score, max = 100, completeness }: ScoreBarProps) {
  if (score === null) return <span className="text-zinc-600">--</span>;

  const pct = (score / max) * 100;
  const color = score >= 80 ? "bg-green-500" : score >= 70 ? "bg-yellow-500" : "bg-zinc-600";
  const label = score >= 80 ? "TRADE" : score >= 70 ? "WATCHLIST" : "PASS";

  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-2 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm font-mono">{score}</span>
      <span className={`text-xs px-1.5 py-0.5 rounded ${
        score >= 80 ? "bg-green-500/20 text-green-400" :
        score >= 70 ? "bg-yellow-500/20 text-yellow-400" :
        "bg-zinc-700/50 text-zinc-400"
      }`}>{label}</span>
      {completeness !== null && completeness !== undefined && (
        <span className="text-xs text-zinc-500">{completeness}/8</span>
      )}
    </div>
  );
}

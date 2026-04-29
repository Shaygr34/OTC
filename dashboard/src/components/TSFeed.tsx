import type { Trade } from "@/lib/types";

export default function TSFeed({ trades }: { trades: Trade[] }) {
  if (!trades.length)
    return <div className="text-zinc-600 text-xs">No trades yet</div>;

  return (
    <div className="max-h-52 overflow-y-auto">
      <div className="grid grid-cols-4 text-[10px] text-zinc-600 uppercase tracking-wider mb-1.5 px-1">
        <span>Time</span>
        <span>Side</span>
        <span className="text-right">Size</span>
        <span className="text-right">Price</span>
      </div>
      {trades.map((t) => (
        <div key={t.id} className="grid grid-cols-4 text-[11px] font-mono py-0.5 px-1 hover:bg-zinc-800/30 rounded">
          <span className="text-zinc-600">
            {new Date(t.timestamp).toLocaleTimeString()}
          </span>
          <span className={
            t.side === "ask" ? "text-emerald-400" :
            t.side === "bid" ? "text-red-400" :
            "text-zinc-500"
          }>
            {t.side || "?"}
          </span>
          <span className="text-zinc-300 text-right">{Number(t.size).toLocaleString()}</span>
          <span className="text-zinc-400 text-right">${t.price}</span>
        </div>
      ))}
    </div>
  );
}

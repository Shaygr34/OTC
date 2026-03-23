import type { Trade } from "@/lib/types";

export default function TSFeed({ trades }: { trades: Trade[] }) {
  if (!trades.length) return <div className="text-zinc-500">No trades</div>;

  return (
    <div className="bg-[#1a1a2e] border border-[#2a2a3e] rounded-lg p-4">
      <h3 className="text-sm font-bold mb-3 text-zinc-300">Time & Sales</h3>
      <div className="max-h-48 overflow-y-auto space-y-0.5">
        {trades.map((t) => (
          <div key={t.id} className="flex justify-between text-xs font-mono py-0.5">
            <span className="text-zinc-500 w-20">
              {new Date(t.timestamp).toLocaleTimeString()}
            </span>
            <span className={
              t.side === "ask" ? "text-green-400" :
              t.side === "bid" ? "text-red-400" :
              "text-zinc-400"
            }>
              {t.side || "?"}
            </span>
            <span className="text-zinc-300">{Number(t.size).toLocaleString()}</span>
            <span className="text-zinc-400">${t.price}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

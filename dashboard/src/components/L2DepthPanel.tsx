import type { L2Snapshot } from "@/lib/types";

const BAD_MMS = new Set([
  "MAXM", "GLED", "CFGN", "PAUL", "JANE", "BBAR", "BLAS",
  "ALPS", "STXG", "AEXG", "VFIN", "VERT", "BMAK",
]);

function formatSize(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

export default function L2DepthPanel({ snapshot }: { snapshot: L2Snapshot | null }) {
  if (!snapshot) return <div className="text-zinc-500">No L2 data</div>;

  const ratio = snapshot.total_bid_shares && snapshot.total_ask_shares
    ? (snapshot.total_bid_shares / snapshot.total_ask_shares).toFixed(1)
    : "--";

  return (
    <div className="bg-[#1a1a2e] border border-[#2a2a3e] rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-zinc-300">L2 Depth</h3>
        <span className="text-xs text-zinc-400">
          Ratio: <span className="font-mono font-bold text-white">{ratio}:1</span>
          {" "}({formatSize(snapshot.total_bid_shares || 0)} bid / {formatSize(snapshot.total_ask_shares || 0)} ask)
        </span>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs text-green-400 font-bold mb-2">BIDS</div>
          {(snapshot.bid_levels || []).map((level, i) => (
            <div key={i} className="flex justify-between text-xs py-0.5 font-mono">
              <span className="text-zinc-400">{level.mm_id || "?"}</span>
              <span className="text-green-400">{formatSize(level.size)}</span>
              <span className="text-zinc-500">{level.price}</span>
            </div>
          ))}
        </div>
        <div>
          <div className="text-xs text-red-400 font-bold mb-2">ASKS</div>
          {(snapshot.ask_levels || []).map((level, i) => (
            <div key={i} className="flex justify-between text-xs py-0.5 font-mono">
              <span className="text-zinc-500">{level.price}</span>
              <span className="text-red-400">{formatSize(level.size)}</span>
              <span className={BAD_MMS.has(level.mm_id) ? "text-red-500 font-bold" : "text-zinc-400"}>
                {level.mm_id || "?"}
                {BAD_MMS.has(level.mm_id) && " !!"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

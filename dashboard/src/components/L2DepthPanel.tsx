import type { L2Snapshot } from "@/lib/types";
import Tip from "./Tip";
import { tips } from "@/lib/i18n";

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
  if (!snapshot) return <div className="text-zinc-600 text-xs">No L2 data yet</div>;

  const ratio = snapshot.total_bid_shares && snapshot.total_ask_shares
    ? (snapshot.total_bid_shares / snapshot.total_ask_shares).toFixed(1)
    : "--";

  const ratioNum = parseFloat(ratio) || 0;
  const ratioColor = ratioNum >= 5 ? "text-emerald-400" : ratioNum >= 3 ? "text-amber-400" : "text-red-400";

  return (
    <div>
      <div className="flex items-center gap-3 mb-3 text-xs">
        <Tip en={tips.imbalance.en} he={tips.imbalance.he}>
          <span className="text-zinc-500">Ratio:</span>
        </Tip>
        <span className={`font-mono font-bold text-sm ${ratioColor}`}>{ratio}:1</span>
        <span className="text-zinc-600">
          {formatSize(snapshot.total_bid_shares || 0)} bid / {formatSize(snapshot.total_ask_shares || 0)} ask
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-[10px] text-emerald-500 font-bold mb-1.5 uppercase tracking-wider">Bids</div>
          {(snapshot.bid_levels || []).map((level, i) => (
            <div key={i} className="flex justify-between text-[11px] py-0.5 font-mono">
              <span className="text-zinc-500 w-10">{level.mm_id || "?"}</span>
              <span className="text-emerald-400">{formatSize(level.size)}</span>
              <span className="text-zinc-600">{level.price}</span>
            </div>
          ))}
          {(!snapshot.bid_levels || snapshot.bid_levels.length === 0) && (
            <div className="text-zinc-700 text-[10px]">No bids</div>
          )}
        </div>
        <div>
          <div className="text-[10px] text-red-500 font-bold mb-1.5 uppercase tracking-wider">Asks</div>
          {(snapshot.ask_levels || []).map((level, i) => (
            <div key={i} className="flex justify-between text-[11px] py-0.5 font-mono">
              <span className="text-zinc-600">{level.price}</span>
              <span className="text-red-400">{formatSize(level.size)}</span>
              <span className={BAD_MMS.has(level.mm_id)
                ? "text-red-500 font-bold w-10 text-right"
                : "text-zinc-500 w-10 text-right"
              }>
                {level.mm_id || "?"}
                {BAD_MMS.has(level.mm_id) && (
                  <Tip en={tips.bad_mm.en} he={tips.bad_mm.he}>
                    <span className="text-red-500"> !!</span>
                  </Tip>
                )}
              </span>
            </div>
          ))}
          {(!snapshot.ask_levels || snapshot.ask_levels.length === 0) && (
            <div className="text-zinc-700 text-[10px]">No asks</div>
          )}
        </div>
      </div>
    </div>
  );
}

import type { ScoreDetail } from "@/lib/types";
import Tip from "./Tip";
import { tips, type TipKey } from "@/lib/i18n";

const COMPONENTS: { key: string; tipKey: TipKey }[] = [
  { key: "stability", tipKey: "stability" },
  { key: "l2_imbalance", tipKey: "l2_imbalance" },
  { key: "no_bad_mm", tipKey: "no_bad_mm" },
  { key: "no_vol_anomaly", tipKey: "no_vol_anomaly" },
  { key: "consistent_vol", tipKey: "consistent_vol" },
  { key: "bid_support", tipKey: "bid_support" },
  { key: "ts_ratio", tipKey: "ts_ratio" },
  { key: "dilution_clear", tipKey: "dilution_clear" },
];

export default function ScoreBreakdown({ detail }: { detail: ScoreDetail | null }) {
  if (!detail) return <div className="text-zinc-600 text-xs">No score data yet</div>;

  return (
    <div className="space-y-1.5">
      {COMPONENTS.map(({ key, tipKey }) => {
        const comp = (detail as any)[key];
        if (!comp) return null;
        const tip = tips[tipKey];
        const pct = comp.max > 0 ? (comp.score / comp.max) * 100 : 0;

        return (
          <div key={key} className="flex items-center gap-2 text-xs">
            <span className={`w-36 truncate ${comp.has_data ? "text-zinc-300" : "text-zinc-600"}`}>
              <Tip en={tip.en} he={tip.he}>
                <span>{tip.en}</span>
              </Tip>
            </span>
            <div className="flex-1 h-1.5 bg-zinc-800/50 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  !comp.has_data ? "bg-zinc-700/50" :
                  comp.score === comp.max ? "bg-emerald-500" :
                  comp.score > 0 ? "bg-amber-500" : "bg-red-500"
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="font-mono w-10 text-right text-zinc-400">
              {comp.score}/{comp.max}
            </span>
            {!comp.has_data && (
              <span className="text-[9px] text-zinc-600">no data</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

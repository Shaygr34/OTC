import type { ScoreDetail } from "@/lib/types";

const LABELS: Record<string, string> = {
  stability: "Range Stability (30d)",
  l2_imbalance: "L2 Imbalance",
  no_bad_mm: "No Bad MMs on Ask",
  no_vol_anomaly: "No Volume Anomaly",
  consistent_vol: "Consistent Volume",
  bid_support: "Bid Support",
  ts_ratio: "T&S Ratio Bullish",
  dilution_clear: "Dilution Clear",
};

export default function ScoreBreakdown({ detail }: { detail: ScoreDetail | null }) {
  if (!detail) return <div className="text-zinc-500">No score data</div>;

  return (
    <div className="bg-[#1a1a2e] border border-[#2a2a3e] rounded-lg p-4">
      <h3 className="text-sm font-bold mb-3 text-zinc-300">Score Breakdown</h3>
      <div className="space-y-2">
        {Object.entries(detail).map(([key, comp]) => (
          <div key={key} className="flex items-center justify-between text-sm">
            <span className={comp.has_data ? "text-zinc-300" : "text-zinc-600"}>
              {LABELS[key] || key}
            </span>
            <div className="flex items-center gap-2">
              <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    !comp.has_data ? "bg-zinc-700" :
                    comp.score === comp.max ? "bg-green-500" :
                    comp.score > 0 ? "bg-yellow-500" : "bg-red-500"
                  }`}
                  style={{ width: `${(comp.score / comp.max) * 100}%` }}
                />
              </div>
              <span className="font-mono w-12 text-right">
                {comp.score}/{comp.max}
              </span>
              {!comp.has_data && (
                <span className="text-xs text-zinc-600">no data</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

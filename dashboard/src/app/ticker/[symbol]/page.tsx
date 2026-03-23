"use client";
import { use } from "react";
import Link from "next/link";
import { useTicker } from "@/lib/hooks";
import ScoreBar from "@/components/ScoreBar";
import ScoreBreakdown from "@/components/ScoreBreakdown";
import L2DepthPanel from "@/components/L2DepthPanel";
import TSFeed from "@/components/TSFeed";
import ATMPlan from "@/components/ATMPlan";

export default function TickerDetailPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = use(params);
  const { data, isLoading } = useTicker(symbol);

  if (isLoading) return <div className="text-zinc-500">Loading {symbol}...</div>;
  if (!data?.candidate) return <div className="text-zinc-500">Ticker {symbol} not found.</div>;

  const { candidate, l2_snapshots, trades, alerts } = data;
  const latestL2 = l2_snapshots[0] || null;
  const bidPrice = latestL2?.bid_levels?.[0]?.price || null;

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <Link href="/" className="text-zinc-500 hover:text-zinc-300 text-sm">&larr; Back</Link>
        <h2 className="text-xl font-bold font-mono">{symbol}</h2>
        <span className="text-xs bg-zinc-800 px-2 py-0.5 rounded">{candidate.price_tier}</span>
        <ScoreBar score={candidate.atm_score} completeness={candidate.components_scored} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ScoreBreakdown detail={candidate.score_detail} />
        <ATMPlan candidate={candidate} bidPrice={bidPrice} />
        <L2DepthPanel snapshot={latestL2} />
        <TSFeed trades={trades} />
      </div>

      {alerts.length > 0 && (
        <div className="mt-4 bg-[#1a1a2e] border border-[#2a2a3e] rounded-lg p-4">
          <h3 className="text-sm font-bold mb-2 text-zinc-300">Alerts</h3>
          {alerts.map((a: any) => (
            <div key={a.id} className="flex gap-3 text-xs py-1 border-b border-[#2a2a3e] last:border-0">
              <span className={`px-1.5 py-0.5 rounded ${
                a.severity === "CRITICAL" ? "bg-red-500/20 text-red-400" :
                a.severity === "HIGH" ? "bg-orange-500/20 text-orange-400" :
                a.severity === "WARNING" ? "bg-yellow-500/20 text-yellow-400" :
                "bg-zinc-700/50 text-zinc-400"
              }`}>{a.severity}</span>
              <span className="text-zinc-400">{a.alert_type}</span>
              <span className="text-zinc-300">{a.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

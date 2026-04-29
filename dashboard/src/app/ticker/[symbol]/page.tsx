"use client";
import { use } from "react";
import Link from "next/link";
import { useTicker } from "@/lib/hooks";
import ScoreBar from "@/components/ScoreBar";
import ScoreBreakdown from "@/components/ScoreBreakdown";
import L2DepthPanel from "@/components/L2DepthPanel";
import TSFeed from "@/components/TSFeed";
import ATMPlan from "@/components/ATMPlan";
import Tip from "@/components/Tip";
import { tips } from "@/lib/i18n";

export default function TickerDetailPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = use(params);
  const { data, isLoading } = useTicker(symbol);

  if (isLoading)
    return <div className="text-zinc-600 text-sm py-12 text-center">Loading {symbol}...</div>;
  if (!data?.candidate)
    return (
      <div className="text-zinc-600 text-sm py-12 text-center">
        Ticker <span className="font-mono font-bold text-zinc-400">{symbol}</span> not found.
      </div>
    );

  const { candidate, l2_snapshots, trades, alerts } = data;
  const latestL2 = l2_snapshots[0] || null;
  const bidPrice = latestL2?.bid_levels?.[0]?.price || null;
  const score = candidate.atm_score;
  const signal = score >= 80 ? "TRADE" : score >= 70 ? "WATCH" : "PASS";

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-5">
        <Link href="/" className="text-zinc-600 hover:text-zinc-300 text-xs transition-colors">
          &larr; Back
        </Link>
        <h2 className="text-xl font-bold font-mono text-zinc-100">{symbol}</h2>
        <span className="text-[10px] font-mono bg-zinc-800/50 px-1.5 py-0.5 rounded border border-zinc-700/30">
          {candidate.price_tier}
        </span>
        <ScoreBar score={candidate.atm_score} completeness={candidate.components_scored} />
        <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${
          signal === "TRADE"
            ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20"
            : signal === "WATCH"
              ? "bg-amber-500/15 text-amber-400 border border-amber-500/20"
              : "bg-zinc-700/30 text-zinc-500 border border-zinc-700/30"
        }`}>
          {signal}
        </span>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {/* Score Breakdown */}
        <div className="bg-[#0d0d14] border border-[#1e1e30] rounded-lg p-4">
          <h3 className="text-xs font-bold mb-3 text-zinc-400 uppercase tracking-wider">
            <Tip en={tips.score.en} he={tips.score.he}>
              <span>Score Breakdown</span>
            </Tip>
          </h3>
          <ScoreBreakdown detail={candidate.score_detail} />
        </div>

        {/* ATM Plan */}
        <div className="bg-[#0d0d14] border border-[#1e1e30] rounded-lg p-4">
          <h3 className="text-xs font-bold mb-3 text-zinc-400 uppercase tracking-wider">
            <Tip en={tips.atm_plan.en} he={tips.atm_plan.he}>
              <span>ATM Plan</span>
            </Tip>
          </h3>
          <ATMPlan candidate={candidate} bidPrice={bidPrice} />
        </div>

        {/* L2 Depth */}
        <div className="bg-[#0d0d14] border border-[#1e1e30] rounded-lg p-4">
          <h3 className="text-xs font-bold mb-3 text-zinc-400 uppercase tracking-wider">
            <Tip en={tips.l2_depth.en} he={tips.l2_depth.he}>
              <span>L2 Depth</span>
            </Tip>
          </h3>
          <L2DepthPanel snapshot={latestL2} />
        </div>

        {/* Time & Sales */}
        <div className="bg-[#0d0d14] border border-[#1e1e30] rounded-lg p-4">
          <h3 className="text-xs font-bold mb-3 text-zinc-400 uppercase tracking-wider">
            <Tip en={tips.ts_feed.en} he={tips.ts_feed.he}>
              <span>Time & Sales</span>
            </Tip>
          </h3>
          <TSFeed trades={trades} />
        </div>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="mt-3 bg-[#0d0d14] border border-[#1e1e30] rounded-lg p-4">
          <h3 className="text-xs font-bold mb-2 text-zinc-400 uppercase tracking-wider">
            <Tip en={tips.alerts.en} he={tips.alerts.he}>
              <span>Alerts</span>
            </Tip>
          </h3>
          <div className="space-y-1">
            {alerts.map((a: any) => (
              <div key={a.id} className="flex gap-2 text-xs py-1.5 border-b border-[#1e1e30]/50 last:border-0">
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                  a.severity === "CRITICAL" ? "bg-red-500/15 text-red-400" :
                  a.severity === "HIGH" ? "bg-orange-500/15 text-orange-400" :
                  a.severity === "WARNING" ? "bg-amber-500/15 text-amber-400" :
                  "bg-zinc-700/30 text-zinc-500"
                }`}>{a.severity}</span>
                <span className="text-zinc-500 font-mono">{a.alert_type}</span>
                <span className="text-zinc-300">{a.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

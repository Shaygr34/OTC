"use client";
import Link from "next/link";
import { useCandidates, useScannerStatus } from "@/lib/hooks";
import AddTickerInput from "@/components/AddTickerInput";
import ScoreBar from "@/components/ScoreBar";
import StatusBadge from "@/components/StatusBadge";
import Tip from "@/components/Tip";
import { tips } from "@/lib/i18n";

function SignalBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-zinc-600 text-xs">—</span>;

  if (score >= 80)
    return (
      <Tip en={tips.signal_trade.en} he={tips.signal_trade.he}>
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
          TRADE
        </span>
      </Tip>
    );

  if (score >= 70)
    return (
      <Tip en={tips.signal_watch.en} he={tips.signal_watch.he}>
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/20">
          WATCH
        </span>
      </Tip>
    );

  return (
    <Tip en={tips.signal_pass.en} he={tips.signal_pass.he}>
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] bg-zinc-700/30 text-zinc-500 border border-zinc-700/30">
        PASS
      </span>
    </Tip>
  );
}

function SourceBadge({ status }: { status: string }) {
  if (status === "manual")
    return (
      <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/15">
        MANUAL
      </span>
    );
  return (
    <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/15">
      SCANNER
    </span>
  );
}

function RecentDiscoveries() {
  const { data } = useScannerStatus();
  const recent = data?.recent_discoveries || [];

  if (!recent.length) return null;

  return (
    <div className="mb-4 bg-[#0d0d14] border border-[#1e1e30] rounded-lg p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[10px] text-purple-400 font-bold uppercase tracking-wider">Scanner Discoveries</span>
        <Tip en={tips.scanner.en} he={tips.scanner.he}>
          <span className="text-[10px] text-zinc-600">last 24h</span>
        </Tip>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {recent.map((r: any) => (
          <Link
            key={r.ticker}
            href={`/ticker/${r.ticker}`}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-[#12121a] border border-[#2a2a3e] hover:border-purple-500/30 transition-colors text-xs"
          >
            <span className="font-mono font-bold text-zinc-200">{r.ticker}</span>
            <span className="text-[9px] text-zinc-500">{r.price_tier}</span>
            <span className="text-[9px] text-zinc-600">{r.exchange}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default function WatchlistPage() {
  const { data: candidates, isLoading } = useCandidates();

  // Sort: TRADE first, then WATCHLIST, then by score
  const sorted = [...(candidates || [])].sort((a: any, b: any) => {
    const sa = a.atm_score ?? -1;
    const sb = b.atm_score ?? -1;
    return sb - sa;
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold">
            <Tip en={tips.watchlist.en} he={tips.watchlist.he}>
              <span>Watchlist</span>
            </Tip>
          </h2>
        </div>
        <AddTickerInput />
      </div>

      <RecentDiscoveries />

      {isLoading ? (
        <div className="text-zinc-600 text-sm py-12 text-center">Loading candidates...</div>
      ) : (
        <div className="bg-[#0d0d14] border border-[#1e1e30] rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e1e30] text-[11px] text-zinc-500 uppercase tracking-wider text-left">
                <th className="px-4 py-2.5 font-medium">Ticker</th>
                <th className="px-4 py-2.5 font-medium">
                  <Tip en={tips.tier.en} he={tips.tier.he}><span>Tier</span></Tip>
                </th>
                <th className="px-4 py-2.5 font-medium">
                  <Tip en={tips.score.en} he={tips.score.he}><span>Score</span></Tip>
                </th>
                <th className="px-4 py-2.5 font-medium">Signal</th>
                <th className="px-4 py-2.5 font-medium">Source</th>
                <th className="px-4 py-2.5 font-medium">Exchange</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((c: any) => (
                <tr
                  key={c.ticker}
                  className={`border-b border-[#1e1e30]/50 hover:bg-[#12121a] transition-colors ${
                    c.atm_score >= 80 ? "bg-emerald-500/[0.03]" : ""
                  }`}
                >
                  <td className="px-4 py-2.5">
                    <Link
                      href={`/ticker/${c.ticker}`}
                      className="font-mono font-bold text-zinc-100 hover:text-blue-400 transition-colors"
                    >
                      {c.ticker}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="text-[10px] font-mono bg-zinc-800/50 px-1.5 py-0.5 rounded border border-zinc-700/30">
                      {c.price_tier}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <ScoreBar score={c.atm_score} completeness={c.components_scored} />
                  </td>
                  <td className="px-4 py-2.5">
                    <SignalBadge score={c.atm_score} />
                  </td>
                  <td className="px-4 py-2.5">
                    <SourceBadge status={c.status} />
                  </td>
                  <td className="px-4 py-2.5 text-zinc-500 font-mono text-[10px]">
                    {c.exchange}
                  </td>
                </tr>
              ))}
              {sorted.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-zinc-600 text-sm">
                    No candidates yet. Scanner runs every 15 minutes during market hours.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

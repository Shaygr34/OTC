"use client";
import Link from "next/link";
import { useCandidates } from "@/lib/hooks";
import AddTickerInput from "@/components/AddTickerInput";
import ScoreBar from "@/components/ScoreBar";
import StatusBadge from "@/components/StatusBadge";

export default function WatchlistPage() {
  const { data: candidates, isLoading } = useCandidates();

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">Watchlist</h2>
        <AddTickerInput />
      </div>

      {isLoading ? (
        <div className="text-zinc-500">Loading...</div>
      ) : (
        <div className="bg-[#12121a] border border-[#2a2a3e] rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2a2a3e] text-zinc-400 text-left">
                <th className="px-4 py-3 font-medium">Ticker</th>
                <th className="px-4 py-3 font-medium">Tier</th>
                <th className="px-4 py-3 font-medium">Score</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Exchange</th>
              </tr>
            </thead>
            <tbody>
              {(candidates || []).map((c: any) => (
                <tr
                  key={c.ticker}
                  className="border-b border-[#2a2a3e] hover:bg-[#1a1a2e] transition-colors"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/ticker/${c.ticker}`}
                      className="font-mono font-bold text-blue-400 hover:text-blue-300"
                    >
                      {c.ticker}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs bg-zinc-800 px-2 py-0.5 rounded">
                      {c.price_tier}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <ScoreBar
                      score={c.atm_score}
                      completeness={c.components_scored}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="px-4 py-3 text-zinc-400 font-mono text-xs">
                    {c.exchange}
                  </td>
                </tr>
              ))}
              {(!candidates || candidates.length === 0) && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-zinc-500">
                    No candidates yet. Add a ticker to get started.
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

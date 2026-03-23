import type { Candidate } from "@/lib/types";

const HOLD_TIMES: Record<string, string> = {
  TRIP_ZERO: "4h intraday / 2d overnight",
  TRIPS: "4h intraday / 2d overnight",
  LOW_DUBS: "2 days",
  DUBS: "2 days",
  PENNIES: "5 days max",
};

const PORTFOLIO_VALUE = 10000;
const MAX_POSITION_PCT = 0.05;
const MAX_LOSS_PCT = 0.02;

interface ATMPlanProps {
  candidate: Candidate;
  bidPrice: string | null;
}

export default function ATMPlan({ candidate, bidPrice }: ATMPlanProps) {
  const score = candidate.atm_score;
  const tier = candidate.price_tier;
  const price = bidPrice ? parseFloat(bidPrice) : null;

  const positionValue = PORTFOLIO_VALUE * MAX_POSITION_PCT;
  const shares = price && price > 0 ? Math.floor(positionValue / price) : null;
  const maxLoss = PORTFOLIO_VALUE * MAX_LOSS_PCT;
  const holdTime = HOLD_TIMES[tier] || "Unknown";

  const action = score !== null && score >= 80 ? "TRADE" : score !== null && score >= 70 ? "WATCHLIST" : "PASS";

  const dil = candidate.score_detail?.dilution_clear;

  return (
    <div className="bg-[#1a1a2e] border border-[#2a2a3e] rounded-lg p-4">
      <h3 className="text-sm font-bold mb-3 text-zinc-300">ATM Plan</h3>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-zinc-500 text-xs">Signal</div>
          <div className={`font-bold ${
            action === "TRADE" ? "text-green-400" :
            action === "WATCHLIST" ? "text-yellow-400" : "text-zinc-400"
          }`}>{action}</div>
        </div>
        <div>
          <div className="text-zinc-500 text-xs">Entry Price</div>
          <div className="font-mono">{bidPrice ? `$${bidPrice}` : "--"}</div>
        </div>
        <div>
          <div className="text-zinc-500 text-xs">Position Size</div>
          <div className="font-mono">
            {shares ? `${shares.toLocaleString()} shares ($${positionValue})` : "--"}
          </div>
        </div>
        <div>
          <div className="text-zinc-500 text-xs">Max Loss</div>
          <div className="font-mono text-red-400">${maxLoss}</div>
        </div>
        <div>
          <div className="text-zinc-500 text-xs">Est. Hold Time</div>
          <div>{holdTime}</div>
        </div>
        <div>
          <div className="text-zinc-500 text-xs">Dilution</div>
          {!dil ? (
            <div className="text-zinc-500">--</div>
          ) : !dil.has_data ? (
            <div className="text-zinc-500">No data</div>
          ) : (
            <div className={dil.score >= 10 ? "text-green-400" : "text-red-400"}>
              {dil.score >= 10 ? "Clear" : "Detected"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

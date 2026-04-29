import type { Candidate } from "@/lib/types";
import Tip from "./Tip";
import { tips } from "@/lib/i18n";

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

  const dil = candidate.score_detail?.dilution_clear;

  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
      <div>
        <div className="text-zinc-600 text-[10px] uppercase tracking-wider">Entry Price</div>
        <div className="font-mono text-zinc-200">{bidPrice ? `$${bidPrice}` : "--"}</div>
      </div>
      <div>
        <Tip en={tips.position_size.en} he={tips.position_size.he}>
          <div className="text-zinc-600 text-[10px] uppercase tracking-wider">Position Size</div>
        </Tip>
        <div className="font-mono text-zinc-200">
          {shares ? `${shares.toLocaleString()} shares ($${positionValue})` : "--"}
        </div>
      </div>
      <div>
        <Tip en={tips.max_loss.en} he={tips.max_loss.he}>
          <div className="text-zinc-600 text-[10px] uppercase tracking-wider">Max Loss</div>
        </Tip>
        <div className="font-mono text-red-400">${maxLoss}</div>
      </div>
      <div>
        <Tip en={tips.hold_time.en} he={tips.hold_time.he}>
          <div className="text-zinc-600 text-[10px] uppercase tracking-wider">Hold Time</div>
        </Tip>
        <div className="text-zinc-200">{holdTime}</div>
      </div>
      <div className="col-span-2">
        <div className="text-zinc-600 text-[10px] uppercase tracking-wider">Dilution</div>
        {!dil ? (
          <div className="text-zinc-600">--</div>
        ) : !dil.has_data ? (
          <div className="text-zinc-600">No data</div>
        ) : (
          <div className={dil.score >= 10 ? "text-emerald-400" : "text-red-400"}>
            {dil.score >= 10 ? "Clear" : "Detected"}
          </div>
        )}
      </div>
    </div>
  );
}

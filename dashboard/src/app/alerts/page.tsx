"use client";
import { useAlerts } from "@/lib/hooks";
import Link from "next/link";

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "bg-red-500/20 text-red-400",
  HIGH: "bg-orange-500/20 text-orange-400",
  WARNING: "bg-yellow-500/20 text-yellow-400",
  INFO: "bg-zinc-700/50 text-zinc-400",
};

export default function AlertsPage() {
  const { data: alerts, isLoading } = useAlerts();

  return (
    <div>
      <h2 className="text-xl font-bold mb-6">Alerts</h2>

      {isLoading ? (
        <div className="text-zinc-500">Loading...</div>
      ) : (
        <div className="bg-[#12121a] border border-[#2a2a3e] rounded-lg overflow-hidden">
          {(alerts || []).length === 0 ? (
            <div className="px-4 py-8 text-center text-zinc-500">No alerts.</div>
          ) : (
            <div className="divide-y divide-[#2a2a3e]">
              {(alerts || []).map((a: any) => (
                <div key={a.id} className="flex items-center gap-4 px-4 py-3 text-sm">
                  <span className="text-zinc-500 text-xs font-mono w-20">
                    {new Date(a.timestamp).toLocaleTimeString()}
                  </span>
                  <span className={`px-2 py-0.5 rounded text-xs ${SEVERITY_COLORS[a.severity] || ""}`}>
                    {a.severity}
                  </span>
                  <Link href={`/ticker/${a.ticker}`} className="font-mono text-blue-400 hover:text-blue-300">
                    {a.ticker}
                  </Link>
                  <span className="text-zinc-400 text-xs">{a.alert_type}</span>
                  <span className="text-zinc-300 flex-1">{a.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

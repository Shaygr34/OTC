"use client";
import { useHealth } from "@/lib/hooks";

export default function ConnectionStatus() {
  const { data } = useHealth();
  const status = data?.engine_status || "disconnected";

  const configs = {
    connected: { color: "bg-green-500", label: "Engine Connected" },
    stale: { color: "bg-yellow-500", label: "Engine Stale" },
    disconnected: { color: "bg-red-500", label: "Engine Offline" },
  };
  const config = configs[status as keyof typeof configs] || configs.disconnected;

  return (
    <div className="flex items-center gap-2 text-sm">
      <div className={`w-2 h-2 rounded-full ${config.color} animate-pulse`} />
      <span className="text-zinc-400">{config.label}</span>
      {data && (
        <span className="text-zinc-600 text-xs">
          {data.active_tickers} active / {data.pending_tickers} pending
        </span>
      )}
    </div>
  );
}

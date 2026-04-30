"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useHealth, useScannerStatus } from "@/lib/hooks";

const NAV_ITEMS = [
  { href: "/", label: "Watchlist", he: "רשימת מעקב", icon: "◉" },
  { href: "/alerts", label: "Alerts", he: "התראות", icon: "⚡" },
];

function EngineIndicator() {
  const { data } = useHealth();
  const status = data?.engine_status || "disconnected";

  const marketOpen = data?.market_open ?? false;

  const configs = {
    connected: { color: "bg-emerald-500", ring: "ring-emerald-500/30", label: "Engine Live" },
    stale: { color: "bg-amber-500", ring: "ring-amber-500/30", label: marketOpen ? "Engine Stale" : "Engine Idle" },
    disconnected: { color: "bg-red-500", ring: "ring-red-500/30", label: "Engine Offline" },
  };
  const c = configs[status as keyof typeof configs] || configs.disconnected;

  return (
    <div className="px-3 py-2.5 bg-[#0d0d14] rounded-lg border border-[#1e1e30]">
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${c.color} ring-4 ${c.ring} ${status === "connected" ? "animate-pulse" : ""}`} />
        <span className="text-xs text-zinc-300">{c.label}</span>
      </div>
      {data && (
        <div className="mt-1.5 space-y-0.5">
          <div className="flex gap-3 text-[10px] text-zinc-500">
            <span>{data.active_tickers} active</span>
            <span>{data.pending_tickers} pending</span>
          </div>
          <div className="text-[9px] text-zinc-600">
            {marketOpen ? "US Market Open" : "US Market Closed"}
          </div>
        </div>
      )}
    </div>
  );
}

function ScannerIndicator() {
  const { data } = useScannerStatus();

  return (
    <div className="px-3 py-2.5 bg-[#0d0d14] rounded-lg border border-[#1e1e30]">
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-zinc-500">SCANNER</span>
        <span className="text-[10px] text-zinc-600">every 15m</span>
      </div>
      {data && (
        <div className="mt-1.5 space-y-0.5">
          <div className="flex justify-between text-[10px]">
            <span className="text-zinc-500">Last hour</span>
            <span className="text-zinc-300 font-mono">{data.discovered_last_hour || 0} new</span>
          </div>
          <div className="flex justify-between text-[10px]">
            <span className="text-zinc-500">Last 24h</span>
            <span className="text-zinc-300 font-mono">{data.discovered_last_24h || 0} new</span>
          </div>
          <div className="flex justify-between text-[10px]">
            <span className="text-zinc-500">Total</span>
            <span className="text-zinc-300 font-mono">{data.total_candidates || 0}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-60 h-screen bg-[#0a0a12] border-r border-[#1e1e30] flex flex-col fixed">
      {/* Header */}
      <div className="px-4 py-5 border-b border-[#1e1e30]">
        <h1 className="text-base font-bold tracking-tight text-zinc-100">ATM Engine</h1>
        <p className="text-[10px] text-zinc-600 mt-0.5 font-mono">OTC Decision Support v0.5</p>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-0.5 p-3">
        {NAV_ITEMS.map(({ href, label, he, icon }) => (
          <Link
            key={href}
            href={href}
            className={`flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-all ${
              pathname === href
                ? "bg-[#1a1a2e] text-white border border-[#2a2a3e]"
                : "text-zinc-500 hover:text-zinc-200 hover:bg-[#12121a]"
            }`}
          >
            <span className="text-xs opacity-60">{icon}</span>
            <span>{label}</span>
            <span className="text-[10px] text-zinc-600 mr-0" dir="rtl">{he}</span>
          </Link>
        ))}
      </nav>

      {/* Status panels */}
      <div className="mt-auto p-3 space-y-2 border-t border-[#1e1e30]">
        <ScannerIndicator />
        <EngineIndicator />
      </div>
    </aside>
  );
}

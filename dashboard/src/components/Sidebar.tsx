"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import ConnectionStatus from "./ConnectionStatus";

const NAV_ITEMS = [
  { href: "/", label: "Watchlist" },
  { href: "/alerts", label: "Alerts" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 h-screen bg-[#12121a] border-r border-[#2a2a3e] flex flex-col p-4 fixed">
      <div className="mb-8">
        <h1 className="text-lg font-bold tracking-tight">ATM Engine</h1>
        <p className="text-xs text-zinc-500 mt-1">OTC Decision Support</p>
      </div>
      <nav className="flex flex-col gap-1">
        {NAV_ITEMS.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={`px-3 py-2 rounded-md text-sm ${
              pathname === href
                ? "bg-[#1a1a2e] text-white"
                : "text-zinc-400 hover:text-white hover:bg-[#1a1a2e]/50"
            }`}
          >
            {label}
          </Link>
        ))}
      </nav>
      <div className="mt-auto">
        <ConnectionStatus />
      </div>
    </aside>
  );
}

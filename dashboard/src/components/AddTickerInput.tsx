"use client";
import { useState } from "react";
import { mutate } from "swr";

export default function AddTickerInput() {
  const [ticker, setTicker] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ticker.trim()) return;
    setLoading(true);
    try {
      await fetch("/api/candidates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: ticker.trim() }),
      });
      mutate("/api/candidates");
      setTicker("");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={ticker}
        onChange={(e) => setTicker(e.target.value.toUpperCase())}
        placeholder="Enter ticker..."
        className="bg-[#1a1a2e] border border-[#2a2a3e] rounded-md px-3 py-1.5 text-sm font-mono focus:outline-none focus:border-blue-500 w-40"
      />
      <button
        type="submit"
        disabled={loading || !ticker.trim()}
        className="bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-700 text-white text-sm px-4 py-1.5 rounded-md transition-colors"
      >
        {loading ? "..." : "Add"}
      </button>
    </form>
  );
}

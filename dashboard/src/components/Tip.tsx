"use client";
import { useState } from "react";

interface TipProps {
  en: string;
  he: string;
  children: React.ReactNode;
}

/**
 * Hebrew tooltip wrapper. Shows (ⓘ) icon that reveals Hebrew explanation on hover.
 * The English label is always visible; Hebrew appears on hover.
 */
export default function Tip({ en, he, children }: TipProps) {
  const [show, setShow] = useState(false);

  return (
    <span className="relative inline-flex items-center gap-1">
      {children}
      <span
        className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-zinc-700/50 text-zinc-500 text-[9px] cursor-help hover:bg-zinc-600/50 hover:text-zinc-300 transition-colors"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
      >
        i
      </span>
      {show && (
        <span className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-[#1a1a2e] border border-[#2a2a3e] rounded-lg shadow-xl text-xs whitespace-nowrap">
          <span className="block text-zinc-300 font-medium" dir="rtl">{he}</span>
          <span className="block text-zinc-500 mt-0.5">{en}</span>
        </span>
      )}
    </span>
  );
}

const STATUS_COLORS: Record<string, string> = {
  active: "bg-green-500/20 text-green-400",
  manual: "bg-blue-500/20 text-blue-400",
  rejected: "bg-red-500/20 text-red-400",
  watching: "bg-yellow-500/20 text-yellow-400",
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_COLORS[status] || "bg-zinc-700 text-zinc-400"}`}>
      {status}
    </span>
  );
}

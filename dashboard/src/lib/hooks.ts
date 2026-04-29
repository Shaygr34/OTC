import useSWR from "swr";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function useCandidates() {
  return useSWR("/api/candidates", fetcher, { refreshInterval: 5000 });
}

export function useTicker(symbol: string) {
  return useSWR(`/api/ticker/${symbol}`, fetcher, { refreshInterval: 5000 });
}

export function useAlerts(severity?: string, ticker?: string) {
  const params = new URLSearchParams();
  if (severity) params.set("severity", severity);
  if (ticker) params.set("ticker", ticker);
  const qs = params.toString();
  return useSWR(`/api/alerts${qs ? `?${qs}` : ""}`, fetcher, { refreshInterval: 5000 });
}

export function useHealth() {
  return useSWR("/api/health", fetcher, { refreshInterval: 5000 });
}

export function useScannerStatus() {
  return useSWR("/api/scanner-status", fetcher, { refreshInterval: 15000 });
}

import { NextResponse } from "next/server";
import { getAlerts } from "@/lib/queries";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const severity = searchParams.get("severity") || undefined;
    const ticker = searchParams.get("ticker") || undefined;
    const alerts = await getAlerts(severity, ticker);
    return NextResponse.json(alerts);
  } catch (error) {
    console.error("Failed to fetch alerts:", error);
    return NextResponse.json({ error: "Database error" }, { status: 500 });
  }
}

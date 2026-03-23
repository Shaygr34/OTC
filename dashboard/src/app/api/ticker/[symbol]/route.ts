import { NextResponse } from "next/server";
import { getTickerData } from "@/lib/queries";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  try {
    const { symbol } = await params;
    const data = await getTickerData(symbol.toUpperCase());
    if (!data.candidate) {
      return NextResponse.json({ error: "Ticker not found" }, { status: 404 });
    }
    return NextResponse.json(data);
  } catch (error) {
    console.error("Failed to fetch ticker data:", error);
    return NextResponse.json({ error: "Database error" }, { status: 500 });
  }
}

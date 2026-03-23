import { NextResponse } from "next/server";
import { getCandidates, addCandidate } from "@/lib/queries";

export async function GET() {
  try {
    const candidates = await getCandidates();
    return NextResponse.json(candidates);
  } catch (error) {
    console.error("Failed to fetch candidates:", error);
    return NextResponse.json({ error: "Database error" }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const { ticker } = await request.json();
    if (!ticker || typeof ticker !== "string") {
      return NextResponse.json({ error: "ticker is required" }, { status: 400 });
    }
    const created = await addCandidate(ticker);
    return NextResponse.json({ ticker: ticker.toUpperCase().trim(), created }, {
      status: created ? 201 : 200,
    });
  } catch (error) {
    console.error("Failed to add candidate:", error);
    return NextResponse.json({ error: "Database error" }, { status: 500 });
  }
}

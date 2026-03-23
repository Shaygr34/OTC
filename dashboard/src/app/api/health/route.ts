import { NextResponse } from "next/server";
import { getHealth } from "@/lib/queries";

export async function GET() {
  try {
    const health = await getHealth();
    return NextResponse.json(health);
  } catch (error) {
    console.error("Health check failed:", error);
    return NextResponse.json(
      { engine_status: "disconnected", error: "Database unreachable" },
      { status: 503 }
    );
  }
}

import { NextResponse } from "next/server";
import pool from "@/lib/db";

export async function GET() {
  try {
    const { rows } = await pool.query(`
      SELECT
        COUNT(*) FILTER (WHERE first_seen > NOW() - INTERVAL '1 hour') as discovered_last_hour,
        COUNT(*) FILTER (WHERE first_seen > NOW() - INTERVAL '24 hours') as discovered_last_24h,
        COUNT(*) as total_candidates,
        MAX(first_seen) as last_discovery,
        COUNT(*) FILTER (WHERE status = 'active') as active,
        COUNT(*) FILTER (WHERE status = 'manual') as manual,
        COUNT(*) FILTER (WHERE status = 'rejected') as rejected
      FROM candidates
    `);

    // Get recently discovered tickers (last 24h)
    const recent = await pool.query(`
      SELECT ticker, price_tier, exchange, first_seen, status
      FROM candidates
      WHERE first_seen > NOW() - INTERVAL '24 hours'
      ORDER BY first_seen DESC
      LIMIT 20
    `);

    return NextResponse.json({
      ...rows[0],
      recent_discoveries: recent.rows,
    });
  } catch (err) {
    console.error("Scanner status error:", err);
    return NextResponse.json({ error: "Failed to fetch scanner status" }, { status: 500 });
  }
}

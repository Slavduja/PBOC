import { NextResponse } from "next/server";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";
import fs from "fs";

const execP = promisify(exec);

// Never cache; always run fresh.
export const dynamic = "force-dynamic";
export const maxDuration = 300;

/**
 * POST /api/refresh
 * Runs the incremental scrape + dashboard export against the project root
 * (the parent of this Next.js app), then returns the new as-of date.
 */
export async function POST() {
  const root = path.join(process.cwd(), ".."); // project root holds the python scripts
  const cmd =
    "python3 pboc_scraper.py --incremental && python3 export_dashboard_data.py";

  try {
    const { stdout } = await execP(cmd, {
      cwd: root,
      timeout: 240000,
      maxBuffer: 1024 * 1024 * 16,
      env: { ...process.env, PYTHONWARNINGS: "ignore" },
    });

    const jsonPath = path.join(process.cwd(), "public", "dashboard_data.json");
    const data = JSON.parse(fs.readFileSync(jsonPath, "utf8"));

    // pull the scraper's coverage line if present, for a friendly message
    const cov = (stdout.match(/YoY coverage:.*/) || [""])[0].trim();

    return NextResponse.json({
      ok: true,
      asof: data.meta.asof,
      points: data.series.length,
      message: cov || "updated",
    });
  } catch (e) {
    const detail = String(e.stderr || e.stdout || e.message || e).slice(-1000);
    return NextResponse.json({ ok: false, error: detail }, { status: 500 });
  }
}

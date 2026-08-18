// Static-export build for Netlify.
// The /api/refresh route runs Python (child_process) and can't exist in a static
// export, so we temporarily move app/api out of the way, build to ./out, restore.
import { execSync } from "child_process";
import fs from "fs";
import path from "path";

const root = path.join(process.cwd());
const api = path.join(root, "app", "api");
const hidden = path.join(root, ".api_hidden");
const hasApi = fs.existsSync(api);

try {
  if (hasApi) fs.renameSync(api, hidden);
  execSync("next build", {
    stdio: "inherit",
    env: { ...process.env, STATIC_EXPORT: "1", NEXT_PUBLIC_STATIC: "1" },
  });
  console.log("\n✓ Static site written to ./out — deploy that folder to Netlify.");
} finally {
  if (hasApi && fs.existsSync(hidden)) fs.renameSync(hidden, api);
}

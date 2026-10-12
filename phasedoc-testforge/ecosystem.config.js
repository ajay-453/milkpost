// PM2 process definition for the MilkPost TestForge-fix (F) arc cockpit.
// One shared cockpit codebase (hub/phasedoc/cockpit.py), parameterized by env.
// Start:   pm2 start ecosystem.config.js   Persist: pm2 save
const path = require("path");
const HUB = path.join(__dirname, "..");
module.exports = {
  apps: [
    {
      name: "phasedoc-testforge",
      script: path.join(HUB, "phasedoc", "cockpit.py"),
      interpreter: "python3",
      cwd: __dirname,
      env: {
        PHASEDOC_PORT: "6808",
        PHASEDOC_DB: path.join(__dirname, "tasks.db"),
        PHASEDOC_ARCH: path.join(__dirname, "architecture.md"),
        PHASEDOC_RESOURCES: path.join(__dirname, "resources.json"),
        PHASEDOC_EXPLAINERS: path.join(__dirname, "explainers.json"),
        PHASEDOC_TITLE: "MilkPost TestForge-fix (F) arc — phasedoc",
        PHASEDOC_SUBTITLE: "internal build tracking · started 2026-10-12 · fixes from the testforge.run scan of ajay-453/milkpost · not for public exposure",
      },
      autorestart: true, max_restarts: 10, min_uptime: "10s", restart_delay: 2000, time: true,
      out_file: ".pm2/phasedoc-testforge-out.log", error_file: ".pm2/phasedoc-testforge-err.log",
    },
  ],
};

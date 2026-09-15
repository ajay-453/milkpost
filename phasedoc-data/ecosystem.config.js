// PM2 process definitions for the phasedoc cockpits.
// One shared cockpit codebase (phasedoc/cockpit.py), parameterized by env.
// Start:   pm2 start ecosystem.config.js
// Persist: pm2 save
//
// Written 2026-09-15 after a reboot + a pm2 dump overwrite (the voice arc's
// `pm2 save` replaced the dump) silently dropped these processes. Keeping the
// definitions in a committed ecosystem file makes the restore one command.
const path = require("path");
const HUB = path.join(__dirname, "..");
module.exports = {
  apps: [
    {
      name: "phasedoc-dataarc",
      script: path.join(HUB, "phasedoc", "cockpit.py"),
      interpreter: "python3",
      cwd: __dirname,
      env: {
        PHASEDOC_PORT: "6791",
        PHASEDOC_DB: path.join(__dirname, "tasks.db"),
        PHASEDOC_ARCH: path.join(__dirname, "architecture.md"),
        PHASEDOC_RESOURCES: path.join(__dirname, "resources.json"),
        PHASEDOC_EXPLAINERS: path.join(__dirname, "explainers.json"),
        PHASEDOC_ARTIFACTS: path.join(__dirname, "artifacts.json"),
        PHASEDOC_TITLE: "Barnboard Data Platform — phasedoc",
        PHASEDOC_SUBTITLE:
          "internal build tracking · arc closed 27/27 · not for public exposure",
      },
      autorestart: true,
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 2000,
      time: true,
      out_file: ".pm2/phasedoc-dataarc-out.log",
      error_file: ".pm2/phasedoc-dataarc-err.log",
    },
    {
      name: "phasedoc-barnboard",
      script: path.join(HUB, "phasedoc", "cockpit.py"),
      interpreter: "python3",
      cwd: path.join(HUB, "phasedoc"),
      env: {
        PHASEDOC_PORT: "6789",
      },
      autorestart: true,
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 2000,
      time: true,
      out_file: ".pm2/phasedoc-barnboard-out.log",
      error_file: ".pm2/phasedoc-barnboard-err.log",
    },
  ],
};

// PM2 process definition for Barnboard.
// Start:   pm2 start ecosystem.config.js
// Persist: pm2 save   (then run the `pm2 startup` command once, with sudo)
module.exports = {
  apps: [
    {
      name: "barnboard",
      // Run the app's own virtualenv Python, not the system one.
      script: ".venv/bin/python",
      args: "-m uvicorn app.main:app --host 0.0.0.0 --port 8321",
      interpreter: "none",          // args are a full command; don't wrap in node
      cwd: __dirname,               // the app/ directory (holds app/, .venv, templates)
      env: {
        DB_PATH: "./barnboard.db",  // relative to cwd; the farm's single data file
        APP_NAME: "Barnboard",
        CURRENCY: "₹",
      },
      autorestart: true,            // restart on crash
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 2000,
      max_memory_restart: "300M",
      time: true,                   // timestamp log lines
      out_file: ".pm2/barnboard-out.log",
      error_file: ".pm2/barnboard-err.log",
    },
  ],
};

// PM2 process definition for the Barnboard DATA PLATFORM betadoc.
// One shared server codebase (betadoc/betadoc_server.py), parameterized by env
// — this folder holds only this betadoc's site and config.
// Start:   pm2 start ecosystem.config.js
// Persist: pm2 save
const path = require("path");
module.exports = {
  apps: [
    {
      name: "betadoc-dataplatform",
      script: path.join(__dirname, "../betadoc/betadoc_server.py"),
      interpreter: "python3",
      cwd: __dirname,
      env: {
        BETADOC_PORT: "6790",            // THE betadoc port, fixed (2026-09-09 decision)
        BETADOC_BIND: "0.0.0.0",
        BETADOC_PIN: "8437",
        BETADOC_SHOW_PIN: "0",  // email-first flow: PIN is granted at /demo/request             // rotated 2026-09-09: delivered via /demo/request only
        BETADOC_REQUESTS: path.join(__dirname, ".demo-requests.jsonl"),
        OWNER_EMAIL: "ajaycse777@gmail.com",
        BETADOC_APP_TOKEN_FILE: "/home/oc/velocity/hub/.secrets/local-feed-token.txt",
        RESEND_FROM: "Barnboard <hello@mydairyfarm.online>",
        RESEND_KEY_FILE: "/home/oc/velocity/hub/.secrets/resend-key.txt",  // create this file to enable email   // gets a copy of each PIN email (when SMTP is on)
        // To enable real email delivery, set: SMTP_HOST, SMTP_PORT, SMTP_USER,
        // SMTP_PASS (e.g. a Gmail app password), SMTP_FROM. Until then the PIN
        // is revealed on screen after the email is captured.
        BETADOC_SITE: path.join(__dirname, "site"),
        BETADOC_SECRET_FILE: path.join(__dirname, ".betadoc-secret"),
        BETADOC_COOKIE: "bdd_demo",      // distinct: same-host ports share a cookie jar
        APP_UPSTREAM: "http://127.0.0.1:8321",
        BETADOC_TLS_CERT: "/home/oc/velocity/hub/.secrets/betadoc-cert.pem",
        BETADOC_TLS_KEY: "/home/oc/velocity/hub/.secrets/betadoc-key.pem",
      },
      autorestart: true,
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 2000,
      time: true,
      out_file: ".pm2/betadoc-data-out.log",
      error_file: ".pm2/betadoc-data-err.log",
    },
  ],
};

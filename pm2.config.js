// PM2 process configuration — PageRails on Mac Mini
// Start:   pm2 start pm2.config.js
// Status:  pm2 status
// Logs:    pm2 logs
// Restart: pm2 restart all

const ROOT = __dirname;

module.exports = {
  apps: [
    {
      name:        "pagerails-api",
      cwd:         `${ROOT}/backend`,
      interpreter: `${ROOT}/.venv/bin/python3`,
      script:      `${ROOT}/.venv/bin/uvicorn`,
      args:        "app.main:app --host 0.0.0.0 --port 8000 --workers 2",
      env: {
        PYTHONPATH: `${ROOT}/backend:${ROOT}/pcg_recon`,
      },
      watch:        false,
      autorestart:  true,
      restart_delay: 3000,
      max_restarts: 10,
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    },
    {
      name:        "pagerails-web",
      cwd:         `${ROOT}/frontend`,
      script:      "node_modules/.bin/next",
      args:        "start --port 3000 --hostname 0.0.0.0",
      env: {
        NODE_ENV:            "production",
        NEXT_PUBLIC_API_URL: "http://localhost:8000",
      },
      watch:        false,
      autorestart:  true,
      restart_delay: 3000,
      max_restarts: 10,
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    },
  ],
};

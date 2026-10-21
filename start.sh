#!/bin/bash
# Start both backend and frontend dev servers
set -e

echo "Starting PageRails..."
echo ""

# Backend (FastAPI on :8000)
echo "[backend] Starting FastAPI on http://localhost:8000"
cd "$(dirname "$0")/backend"
uvicorn app.main:app --port 8000 --reload &
BACKEND_PID=$!

# Wait for backend
sleep 2
echo "[backend] API docs: http://localhost:8000/docs"
echo ""

# Frontend (Next.js on :3000)
echo "[frontend] Starting Next.js on http://localhost:3000"
cd "$(dirname "$0")/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Both servers running."
echo "  Frontend:  http://localhost:3000"
echo "  Backend:   http://localhost:8000"
echo "  API docs:  http://localhost:8000/docs"
echo ""
echo "  Login:     obasi@pagecapital.ng / recon2026  (maker)"
echo "             damilola@pagecapital.ng / checker2026  (checker)"
echo ""
echo "Press Ctrl+C to stop both."
echo ""

# Wait for either to exit
wait $BACKEND_PID $FRONTEND_PID

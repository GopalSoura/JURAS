# JURAS MVP — Purani Mandi
Risk-intelligence frontend (React + Vite + TypeScript) and FastAPI REST backend.
The frontend's built-in simulator is enabled by default; the current REST backend
does not yet implement the frontend's optional WebSocket feed.

## Start backend (Windows)
```powershell
cd backend
py -3.13 -m venv .venv313
.\.venv313\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```
The pinned backend dependencies require Python 3.11 or newer.
API docs: http://127.0.0.1:8000/docs

## Start frontend
```powershell
cd frontend
npm install
npm run dev
```
Frontend: http://localhost:5173

The risk-console UI runs in simulator mode by default. See [frontend/README.md](frontend/README.md)
for the optional WebSocket message contract and demo controls.

Backend CORS currently permits localhost:5173. Data is in-memory for this first runnable scaffold;
Member 1 should replace it with PostgreSQL/PostGIS in Sprint task 2.

# JURAS MVP — Purani Mandi
React + Vite + TypeScript frontend, FastAPI backend, simulation-first sensors.

## Start backend (Windows)
```powershell
cd backend
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
API docs: http://127.0.0.1:8000/docs

## Start frontend
```powershell
cd frontend
npm install
npm run dev
```
Frontend: http://localhost:5173

Backend CORS currently permits localhost:5173. Data is in-memory for this first runnable scaffold;
Member 1 should replace it with PostgreSQL/PostGIS in Sprint task 2.

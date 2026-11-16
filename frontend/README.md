# TrackFlow Frontend

Responsive React + Vite dashboard for the TrackFlow synthetic railway traffic optimization prototype.

## Run
Open PowerShell in this folder and run:

```powershell
npm install
npm run dev
```

Open the local URL Vite prints (usually http://localhost:5173). Keep the FastAPI backend running at http://127.0.0.1:8000.

The dashboard calls `GET /api/simulation/baseline` and `GET /api/optimization`. Set `VITE_API_BASE_URL` in a `.env` file if the backend URL differs.

Note: the network diagram is illustrative. This is a synthetic decision-support prototype, not a certified railway safety system.

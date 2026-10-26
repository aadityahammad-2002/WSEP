
# WindSight — Wind Energy Forecasting & Decision Intelligence

A full-stack web application for analysing UK day-ahead wind generation forecasts, comparing predicted output with actual generation, and assessing forecasting uncertainty to support electricity procurement decisions.

## 🚀 Live Application

- **Live Website (Vercel):** https://frontend-aaditya-dev.vercel.app/
- **Live Website (Render):** https://wsep-ayf9.onrender.com/
- **GitHub Repository:** https://github.com/aadityahammad-2002/WSEP
- **Youtube Presentation (Youtube):** https://youtu.be/TTZFjiWVFYs 

## 📌 Overview

WindSight helps UK electricity utilities understand wind power availability before making day-ahead electricity purchasing decisions.

The application uses real Elexon BMRS data to evaluate forecast accuracy and identify potential wind generation shortfalls.

The original assignment focuses on January 2026, with additional support for historical analysis and live forecasting.

## ✨ Key Features

- **Historical Replay:** Compare previous day-ahead forecasts against actual wind generation.
- **Live Prediction:** Analyse tomorrow's wind generation using available forecast data.
- **Forecast Analytics:** Measure MAE, RMSE, bias and forecast accuracy.
- **Decision Intelligence:** Analyse forecast uncertainty and potential wind shortfalls.
- **Historical Data:** Filter results by date and decision time.
- **Saved Predictions:** Preserve forecasts for later comparison with actual generation.
- **CSV Export:** Download forecast analysis and comparison results.
- **Interactive Dashboard:** Visualise wind generation data with interactive charts.

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | React, TypeScript, Vite |
| Charts | Recharts |
| Backend | Python, FastAPI |
| Data Source | Elexon BMRS API |
| Containerization | Docker |
| Frontend Deployment | Vercel |
| Backend Deployment | Render |
| Version Control | Git & GitHub |

## 📂 Project Structure

```text
WSEP/
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── ForecastWorkspace.tsx
│   │   ├── HistoryPage.tsx
│   │   ├── api.ts
│   │   └── styles.css
│   ├── package.json
│   └── vite.config.ts
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── domain.py
│   │   ├── service.py
│   │   ├── intelligence.py
│   │   ├── elexon.py
│   │   ├── predictions.py
│   │   └── store.py
│   ├── tests/
│   ├── data/
│   ├── requirements.txt
│   └── Dockerfile
│
├── .github/workflows/
├── docker-compose.yml
└── README.md
```

## ⚙️ Installation & Setup

### Prerequisites

- Python 3.12 or 3.13
- Node.js and npm
- Git
- Docker (optional)

### 1. Clone the Repository

```bash
git clone https://github.com/aadityahammad-2002/WSEP.git
cd WSEP
```

### 2. Start Backend (Windows PowerShell)

```powershell
cd backend

py -3.13 -m venv .venv

.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Backend runs at:

http://localhost:8000

API documentation:

http://localhost:8000/docs

### 3. Start Frontend

Open a new terminal in the project root.

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at:

http://localhost:5173

### 4. Run with Docker

Alternatively, run the complete application using Docker:

```bash
docker compose up --build
```

Open:

http://localhost:8000

## 📊 Data Sources

WindSight uses Elexon BMRS data:

**1. WINDFOR — Wind Generation Forecasts**

https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream

**2. FUELHH — Actual Wind Generation**

https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream

The application compares forecasts available before a selected decision cutoff with actual generation recorded for the corresponding delivery periods.

Missing source observations are not replaced with synthetic generation values.

## 📐 Forecast Evaluation

Forecast accuracy is evaluated using:

- **MAE:** Mean Absolute Error
- **RMSE:** Root Mean Squared Error
- **Bias:** Average signed forecast error
- **Shortfall Frequency:** Frequency of actual wind generation falling below forecast
- **Historical Risk Scenarios:** Estimated potential downside based on previous forecast errors

These metrics support decision-making but do not directly calculate electricity procurement quantities.

## 🌐 Deployment

The application uses separate frontend and backend deployments:

**Frontend — Vercel**

https://frontend-aaditya-dev.vercel.app/

**Backend — Render**

https://wsep-ayf9.onrender.com

The frontend communicates with the backend through REST APIs.

The frontend environment variable is configured as:

```env
VITE_API_BASE_URL=https://wsep-ayf9.onrender.com
```

The backend allows the Vercel origin through its CORS configuration.

**Deployment note:** The Render Free instance uses ephemeral storage. Saved predictions and downloaded Elexon data may be lost after service restarts or redeployments unless persistent storage is configured.

## 🧪 Testing

Run backend tests:

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -q tests
```

Build the frontend:

```bash
cd frontend
npm install
npm run build
```

Automated tests cover forecast selection, timestamp handling, error calculations, historical replay and API behaviour.

## ⚠️ Limitations

- Analysis is based on Elexon wind forecast and actual generation data.
- Forecast uncertainty estimates depend on the availability and quality of historical observations.
- Electricity demand, electricity prices and procurement contracts are outside the project scope.
- The application is a decision-support prototype, not an automated trading system.
- Persistent storage, authentication and further production validation are required for operational deployment.

## 🤖 AI Assistance Disclosure

AI tools were used during development for frontend implementation, backend code assistance, forecasting logic, testing suggestions and documentation.

The application uses explicit forecasting calculations and testable analytical methods. Its outputs should be independently verified before operational use.

## 📄 Project Information

Developed as part of a Full Stack Software Engineering technical challenge.

**Primary Objective:** Provide transparent and quantitative analysis of UK day-ahead wind generation forecasts using real Elexon data.

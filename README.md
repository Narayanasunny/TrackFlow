# 🚆 TrackFlow – AI-Powered Railway Traffic Throughput Control

**An Intelligent Railway Traffic Management and Optimization System**

TrackFlow is an AI-powered railway traffic management and decision-support system designed to improve railway network efficiency by detecting track conflicts, analyzing train movements, and optimizing train schedules.

The system combines railway simulation, constraint-based optimization, and Agentic AI to help railway operators understand traffic conditions, manage disruptions, and make better scheduling decisions.

---

## 📌 1. Problem Statement

Railway networks handle multiple trains moving across shared track sections. When several trains use the same track section within a short time interval, conflicts can occur due to overlapping track occupancy or insufficient separation between trains.

Traditional railway scheduling and traffic management can become challenging when unexpected situations occur, such as:

- Train delays.
- Track closures.
- Overlapping train movements.
- Headway violations.
- Increasing congestion across railway sections.

These situations can affect railway throughput, increase delays, and make manual rescheduling difficult.

**TrackFlow addresses these challenges through simulation, automated conflict detection, mathematical optimization, and AI-assisted operational decision support.**

---

## 🎯 2. Project Objectives

The main objectives of TrackFlow are:

1. Simulate railway traffic across multiple stations and track sections.
2. Detect conflicts between trains using track occupancy and minimum headway constraints.
3. Analyze train movements and identify congested track sections.
4. Optimize train departure schedules using constraint-based optimization.
5. Simulate railway disruptions such as train delays and track closures.
6. Generate optimized schedules while satisfying railway operating constraints.
7. Provide explanations and operational insights through an AI-powered Copilot.
8. Help railway operators understand traffic conditions through an interactive dashboard.

---

## ✨ 3. Key Features

### 3.1 Railway Network Simulation

- Simulates train movements across multiple railway stations.
- Models railway stations, track sections, and train schedules.
- Calculates simulated arrival and departure times.
- Tracks train movements across the railway network.

### 3.2 Conflict Detection

Identifies railway traffic conflicts, including:

- **Track Occupancy Overlap:** Two trains occupy the same track section at overlapping times.
- **Headway Violation:** Two trains do not maintain the required minimum time separation.

The system identifies the trains involved, affected track sections, and conflict details.

### 3.3 Dynamic Schedule Optimization

- Uses Google OR-Tools CP-SAT for constraint-based scheduling.
- Adjusts train departure times to resolve conflicts.
- Considers track occupancy and minimum headway requirements.
- Validates the resulting schedule against railway constraints.

### 3.4 Disruption Simulation

Allows operators to simulate unexpected railway situations, including:

- Introducing delays to individual trains.
- Closing selected railway track sections.
- Analyzing the impact of disruptions on train movements.
- Rescheduling affected trains to reduce or eliminate conflicts.

### 3.5 AI-Powered Railway Copilot

TrackFlow includes an AI-powered Copilot built using LangGraph and a Large Language Model.

The Copilot is designed to help railway operators interact with the railway system using natural language.

Its agent capabilities include:

- **Traffic Analysis Agent:** Analyzes railway traffic conditions, conflicts, affected trains, and congested track sections.
- **Dynamic Rescheduling Agent:** Supports schedule optimization and disruption-related rescheduling.
- **Explainability Agent:** Explains optimization decisions and provides understandable operational insights.
- **Natural Language Interaction:** Allows operators to ask questions about railway operations using conversational prompts.

The Copilot uses tools to interact with the railway simulation and optimization components.

### 3.6 Interactive Dashboard

The React dashboard provides different views of railway operations:

- Network Topology.
- Train Operations.
- Conflict Intelligence.
- Disruption Simulator.
- Optimization Results.
- AI Copilot.

---

## 🛠️ 4. Technology Stack

| Component | Technology |
|---|---|
| Frontend | React.js |
| Frontend Build Tool | Vite |
| Backend | Python |
| API Framework | FastAPI |
| AI Orchestration | LangGraph |
| LLM Integration | Groq API |
| Language Model | OpenAI GPT-OSS-20B (via Groq) |
| Optimization Engine | Google OR-Tools CP-SAT |
| Data Storage | JSON |
| API Communication | REST APIs |
| Development Environment | VS Code |

---

## 🏗️ 5. System Architecture

TrackFlow follows a modular architecture that separates the frontend, backend, railway simulation, optimization engine, and AI agents.

```text
                  RAILWAY OPERATOR
                         |
                         v
              REACT + VITE DASHBOARD
                         |
                         v
                  FASTAPI BACKEND
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
    SIMULATION       OPTIMIZATION     LANGGRAPH
       ENGINE          ENGINE          AGENTS
          |              |              |
          v              v              v
    Train Movement   OR-TOOLS CP-SAT   AI COPILOT
    Conflict         Schedule          Traffic Analysis
    Detection        Optimization      Rescheduling
                                       Explainability
          |              |              |
          +--------------+--------------+
                         |
                         v
                SCHEDULE VALIDATION
                         |
                         v
                 OPTIMIZATION RESULTS
                         |
                         v
                 REACT DASHBOARD
```

### Architecture Explanation

1. **Frontend:** Operators interact with the railway dashboard and submit requests.
2. **FastAPI Backend:** Receives requests and connects the frontend with backend services.
3. **Simulation Engine:** Simulates train movements and detects railway traffic conflicts.
4. **Optimization Engine:** Uses OR-Tools CP-SAT to calculate improved train schedules.
5. **LangGraph Agents:** Coordinate AI-assisted traffic analysis, rescheduling, and explanations.
6. **Schedule Validator:** Checks whether generated schedules satisfy the defined railway constraints.
7. **Dashboard:** Displays simulation results, conflicts, and optimization information.

---

## 🧠 6. Understanding the Main Modules

### A. Simulation Engine

The simulation engine models train movements across railway stations and track sections.

It uses input data such as:

- Train IDs.
- Train priorities and schedules.
- Railway station information.
- Track section details.
- Travel times.
- Minimum headway requirements.

It calculates train movements and identifies potential conflicts.

### B. Conflict Detection Engine

The conflict detection module analyzes train movements and checks whether railway constraints are violated.

It detects:

1. Occupancy overlaps.
2. Headway violations.

The results help identify which trains and railway sections require attention.

### C. Optimization Engine

The optimization engine uses Google OR-Tools CP-SAT to solve railway scheduling constraints.

Its purpose is to determine suitable train departure adjustments while respecting railway operating constraints.

The optimizer generates an improved schedule, which is then checked by the schedule validator.

### D. Disruption Simulator

The disruption simulator allows operators to introduce unexpected situations into the railway network.

Examples include:

- Delaying a train.
- Making a track section unavailable.

After introducing a disruption, the system analyzes the affected train movements and performs rescheduling.

### E. LangGraph Agent Workflow

LangGraph is used to organize the AI agent workflow.

The agents interact with railway-related tools to analyze traffic conditions, support rescheduling, and explain results.

The LLM is responsible for understanding natural-language requests and coordinating tool usage. The actual simulation, conflict detection, and optimization calculations are performed by backend logic.

---

## 📂 7. Project Structure

```text
TrackFlow/
│
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── dynamic_rescheduling_agent.py
│   │   │   ├── explainability_agent.py
│   │   │   ├── trackflow_graph.py
│   │   │   └── traffic_analysis_agent.py
│   │   │
│   │   ├── optimization/
│   │   │   └── optimizer.py
│   │   │
│   │   ├── simulation/
│   │   │   ├── __init__.py
│   │   │   └── engine.py
│   │   │
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── schedule_validator.py
│   │
│   └── scripts/
│       └── validate_dataset.py
│
├── data/
│   └── raw/
│       ├── stations.json
│       ├── track_sections.json
│       └── trains.json
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── styles.css
│   │
│   ├── index.html
│   ├── package.json
│   └── package-lock.json
│
├── .gitignore
├── README.md
├── requirements.txt
└── folder_structure.txt
```

---

## ⚙️ 8. Installation and Setup

Follow these instructions to run TrackFlow on your local machine.

### Prerequisites

Install the following:

- Python 3.10 or later.
- Node.js and npm.
- Git.
- Visual Studio Code.

### Step 1: Clone the Repository

Open your terminal and execute:

```bash
git clone https://github.com/Narayanasunny/TrackFlow.git
```

Navigate to the project directory:

```bash
cd TrackFlow
```

### Step 2: Create a Python Virtual Environment

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### Step 3: Install Backend Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables

Create a `.env` file in the project root or in the location expected by your backend configuration.

Add your Groq API key using the environment variable name expected by the application.

Example:

```env
GROQ_API_KEY=your_groq_api_key_here
```

**Important:** Replace the placeholder with your own API key. Never upload your actual `.env` file or API key to GitHub.

### Step 5: Start the Backend Server

From the project root, run:

```bash
uvicorn backend.app.main:app --reload
```

The FastAPI server should start at:

```text
http://127.0.0.1:8000
```

FastAPI interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

### Step 6: Install Frontend Dependencies

Open a second terminal.

Navigate to the frontend directory:

```bash
cd frontend
```

Install the required packages:

```bash
npm install
```

### Step 7: Start the Frontend

```bash
npm run dev
```

Open the local URL displayed by Vite in your browser.

The frontend and backend should both be running for the complete application to work.

---

## 📊 9. Dataset Description

TrackFlow currently uses a synthetic railway dataset.

The dataset contains:

| Dataset | Description |
|---|---|
| `stations.json` | Railway station information |
| `track_sections.json` | Railway track section details |
| `trains.json` | Train schedules and movement information |

### Current Simulation Dataset

- 5 railway stations.
- 8 track sections.
- 10 sample trains.

The dataset is designed to simulate railway traffic conditions and test conflict detection and scheduling optimization.

---

## 🔄 10. Working Workflow

The overall TrackFlow workflow is:

1. Load railway station, track section, and train data.
2. Initialize the railway network simulation.
3. Simulate train movements.
4. Detect track occupancy overlaps and headway violations.
5. Analyze railway traffic conditions.
6. Introduce disruptions when required.
7. Run schedule optimization.
8. Validate the optimized schedule.
9. Display results through the dashboard.
10. Use the AI Copilot to understand railway conditions and optimization decisions.

---

## 🔬 11. Testing and Validation

TrackFlow includes a dataset validation script.

Run the following command from the project root:

```bash
python backend/scripts/validate_dataset.py
```

This script checks the railway dataset for structural and data consistency.

The schedule validator is also used to verify optimized train schedules against the defined railway constraints.

---

## 🚀 12. Future Enhancements

Potential future improvements include:

- General-purpose schedule optimization through the AI Copilot.
- Improved conversational memory for follow-up operational questions.
- More advanced railway scheduling constraints.
- Priority-based train scheduling.
- Real-time railway traffic data integration.
- Larger and more realistic railway datasets.
- Advanced performance evaluation and throughput metrics.
- Improved optimization explainability.
- Enhanced visualization of optimized train movements.

---

## 👨‍💻 13. Development and Version Control

TrackFlow is maintained using Git and GitHub.

Repository:

https://github.com/Narayanasunny/TrackFlow

To download the latest changes:

```bash
git pull origin main
```

To save and upload your changes:

```bash
git add .
git commit -m "Describe your changes"
git push origin main
```

---

## 📌 14. Project Summary

TrackFlow combines railway simulation, conflict detection, mathematical optimization, and Agentic AI to improve railway traffic management.

By integrating FastAPI, React, LangGraph, Groq, and Google OR-Tools CP-SAT, the system provides a platform for analyzing railway traffic, handling simulated disruptions, optimizing train schedules, and supporting operational decision-making.

**TrackFlow aims to make railway traffic management more intelligent, efficient, and explainable.**

---

**Project:** TrackFlow – Train Traffic Throughput Control  
**Repository:** https://github.com/Narayanasunny/TrackFlow  
**Domain:** Artificial Intelligence | Railway Optimization | Agentic AI

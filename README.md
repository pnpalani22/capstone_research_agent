# Deep Research Agent

This repository contains a LangGraph-based research workflow with:

- a FastAPI backend for sessions, research runs, resume actions, and translation
- a React frontend for the main workflow dashboard
- a validation runner for scenario-based testing
- optional Streamlit and CLI/demo entrypoints for quick local exploration

## What This App Does

The application accepts a research question, evaluates guardrails, checks prior history, plans searches, gathers evidence, pauses for human review when needed, publishes a final report, and then allows post-publish translation and speech playback in the UI.

## Tech Stack

- Python
- FastAPI
- LangGraph
- LangChain
- React + Vite
- AJV schema validation in the frontend

## Repository Layout

- `api.py`: FastAPI app used by the React frontend
- `app.py`: helpers for starting and resuming LangGraph runs
- `graph.py`: LangGraph graph definition
- `nodes.py`: workflow node implementations
- `tools.py`: Tavily and Wikipedia tool wiring
- `validate_scenarios.py`: scenario runner against the local API
- `validation_queries.json`: validation suite definitions
- `frontend.py`: optional Streamlit interface
- `demo.py`: minimal graph demo
- `react-frontend/`: main React frontend

## Prerequisites

- Python 3.11+ recommended
- Node.js 18+ recommended
- npm
- OpenAI API access for `ChatOpenAI` and embeddings
- Tavily API access for live web search

## Required Environment Variables

Create a `.env` file in the repository root.

Example:

```env
OPENAI_API_KEY=your_openai_api_key
TAVILY_API_KEY=your_tavily_api_key
```

Notes:

- `OPENAI_API_KEY` is required because the graph uses `ChatOpenAI(model="gpt-4o-mini")` and `OpenAIEmbeddings(model="text-embedding-3-small")`.
- `TAVILY_API_KEY` is required for Tavily-backed search.
- Wikipedia search does not require a key.
- The translation endpoint uses `deep-translator` and does not require an extra API key in this project.

## Python Setup

If you already have `.venv`, activate it. Otherwise create one.

### Windows PowerShell

```powershell
Set-Location "g:\AI Training\captone_project\capstone-projects\capstone_research_agent_bhupen"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### macOS / Linux

```bash
cd /path/to/capstone_research_agent_bhupen
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Frontend Setup

```powershell
Set-Location "g:\AI Training\captone_project\capstone-projects\capstone_research_agent_bhupen\react-frontend"
npm install
```

If your backend will run on the default local address, no extra frontend environment variable is required.

Optional frontend override:

```env
VITE_API_BASE_URL=http://localhost:8000/api
```

## How To Start the Application

You usually run the backend and frontend in separate terminals.

### 1. Start the FastAPI backend

From the repository root:

```powershell
Set-Location "g:\AI Training\captone_project\capstone-projects\capstone_research_agent_bhupen"
.\.venv\Scripts\Activate.ps1
uvicorn api:app --reload
```

Expected backend URL:

- `http://localhost:8000`
- health check: `http://localhost:8000/api/health`

### 2. Start the React frontend

From `react-frontend`:

```powershell
Set-Location "g:\AI Training\captone_project\capstone-projects\capstone_research_agent_bhupen\react-frontend"
npm run dev
```

Expected frontend URL:

- `http://localhost:5173`

### 3. Use the app

Open the frontend in your browser and:

1. Start a new session.
2. Enter a research question.
3. Review guardrails and telemetry.
4. Continue through any history or draft approval checkpoint.
5. After publish, use the translation and speech stage.

## How To Run Validation Scenarios

The validation runner calls the FastAPI backend, so the backend must already be running.

### Run the full validation suite

```powershell
Set-Location "g:\AI Training\captone_project\capstone-projects\capstone_research_agent_bhupen"
.\.venv\Scripts\Activate.ps1
python validate_scenarios.py --base-url http://localhost:8000/api
```

### Run only one category

Examples:

```powershell
python validate_scenarios.py --base-url http://localhost:8000/api --category api_validation
python validate_scenarios.py --base-url http://localhost:8000/api --category guardrail_blocked
python validate_scenarios.py --base-url http://localhost:8000/api --category history_review
python validate_scenarios.py --base-url http://localhost:8000/api --category rerank_validation
```

### Use a custom validation user id

```powershell
python validate_scenarios.py --base-url http://localhost:8000/api --user-id validation-runner-1
```

### What the validation runner checks

- API request validation
- guardrail status and risk flags
- allowed tool policy
- history overlap behavior
- draft review interrupts
- rerank-related metrics
- final report creation for resumable scenarios

## Useful Run Commands

### Backend health check

```powershell
Invoke-WebRequest http://localhost:8000/api/health | Select-Object -ExpandProperty Content
```

### Build the React frontend

```powershell
Set-Location "g:\AI Training\captone_project\capstone-projects\capstone_research_agent_bhupen\react-frontend"
npm run build
```

### Preview the production frontend build

```powershell
Set-Location "g:\AI Training\captone_project\capstone-projects\capstone_research_agent_bhupen\react-frontend"
npm run preview
```

### Run the simple LangGraph demo

```powershell
Set-Location "g:\AI Training\captone_project\capstone-projects\capstone_research_agent_bhupen"
.\.venv\Scripts\Activate.ps1
python demo.py
```

### Run the CLI app entrypoint

```powershell
Set-Location "g:\AI Training\captone_project\capstone-projects\capstone_research_agent_bhupen"
.\.venv\Scripts\Activate.ps1
python app.py
```

### Run the Streamlit UI

```powershell
Set-Location "g:\AI Training\captone_project\capstone-projects\capstone_research_agent_bhupen"
.\.venv\Scripts\Activate.ps1
streamlit run frontend.py
```

## Typical Developer Workflow

### Terminal 1: backend

```powershell
Set-Location "g:\AI Training\captone_project\capstone-projects\capstone_research_agent_bhupen"
.\.venv\Scripts\Activate.ps1
uvicorn api:app --reload
```

### Terminal 2: frontend

```powershell
Set-Location "g:\AI Training\captone_project\capstone-projects\capstone_research_agent_bhupen\react-frontend"
npm run dev
```

### Terminal 3: validation

```powershell
Set-Location "g:\AI Training\captone_project\capstone-projects\capstone_research_agent_bhupen"
.\.venv\Scripts\Activate.ps1
python validate_scenarios.py --base-url http://localhost:8000/api
```

## Translation and Speech Notes

- Translation is available only after a final report is published.
- The backend translation endpoint is `POST /api/translate`.
- The UI stores selected language, recent languages, and tone preference in local storage.
- Speech playback uses the browser `SpeechSynthesis` API, so voice quality depends on installed browser and OS voices.

## Common Problems

### Backend starts but research runs fail

Check:

- `OPENAI_API_KEY` is set correctly
- `TAVILY_API_KEY` is set correctly
- outbound network access is available

### Frontend loads but cannot talk to backend

Check:

- backend is running on `http://localhost:8000`
- frontend is using the correct `VITE_API_BASE_URL`
- CORS allows `http://localhost:5173`

### Validation script fails immediately

Check:

- backend is already running
- `--base-url` matches the backend address
- required API keys are loaded in the backend process

### Translation or speech does not work as expected

Check:

- a final report exists first
- the browser supports speech synthesis
- the selected language has an available voice on your OS/browser
- external translation requests are not blocked by network policy

## Useful Files for New Developers

- `README.md`: setup and run guide
- `validation_queries.json`: scenario definitions
- `validate_scenarios.py`: validation runner logic
- `UI_Workflow_Design.pdf`: workflow and test documentation
- `UI_Workflow_Design_PDF.html`: source used to regenerate the PDF
- `UI_Workflow_Design_PPT.md`: slide-content version of the same training material

## Suggested First Smoke Test

1. Start the backend.
2. Start the React frontend.
3. Submit this query:

```text
How should an enterprise research assistant combine retrieval, chunking, and evaluation guardrails to improve factual reliability?
```

4. Approve the draft if a review checkpoint appears.
5. Confirm the final report appears.
6. Change the language to Spanish or French in the translation section.
7. Click the speech icon and confirm playback starts.

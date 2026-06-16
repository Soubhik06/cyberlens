# CyberLens — India Cybercrime Research Intelligence System

CyberLens is a research-grade intelligence system built for **IIM Bangalore** to study the long-term evolution of cybercrime in India. The platform integrates academic literature, victim complaints, media articles, and official government statistics.

## Project Structure
```
cybercrime_research/
├── data/
│   ├── all_data.xlsx        (Registry containing document indices)
│   └── txt/                 (Plain text copies of registered documents)
├── chroma_db/               (Local persistent vector database created by ingest.py)
├── frontend/                (React + Vite + Tailwind CSS SPA project)
│   ├── src/                 (React source files: Chat, Insights, Explorer, Submit pages)
│   ├── dist/                (Built production assets served by FastAPI)
│   └── package.json
├── backend.py               (FastAPI REST backend serving APIs & static React build)
├── run.py                   (FastAPI local server launcher)
├── ngrok_start.py           (Ngrok public sharing server launcher)
├── ingest.py                (Ingestion, token-based chunking & local embedding script)
├── rag.py                   (RAG search & Gemini LLM query logic)
├── insights.py              (Insights generator, data parser & analysis helper)
├── requirements.txt         (Project package dependencies)
├── .env                     (API configuration secrets)
└── README.md                (Project documentation)
```

---

## Setup & Running Instructions

### 1. Install Dependencies
Install all required Python libraries:
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory and add your Google Gemini API Key and NGROK Auth Token:
```env
GEMINI_API_KEY=your_gemini_api_key_here
NGROK_AUTH_TOKEN=your_ngrok_authtoken_here
```

### 3. Build React Frontend
Navigate to the `frontend` folder, install JavaScript dependencies, and build the static assets:
```bash
cd frontend
npm install
npm run build
cd ..
```

### 4. Ingest Data
Run the ingestion pipeline to parse the Excel registry, read the raw text files, chunk them, embed them using local sentence-transformers, and build the persistent vector store:
```bash
python ingest.py
```

### 5. Run the Application
You can run the application in two ways:

#### A. Run Locally (Intranet Access)
Launch the FastAPI backend serving both API routes and the React static UI:
```bash
python run.py
```
Open `http://localhost:8000` in your web browser.

#### B. Run with Ngrok (Public Demo Link)
Launch the server and automatically set up a public ngrok tunnel:
```bash
python ngrok_start.py
```
Copy and share the generated URL labeled as `SHARE THIS LINK:` in the console.

---

## Features

### 1. Ingestion Pipeline (`ingest.py`)
- Reads the excel sheet sheets `stream_a_scraped` and `stream_b_govt`.
- Splits text into exact **800-token chunks with 100-token overlap** using the `sentence-transformers` tokenizer.
- Creates local embeddings via the **all-MiniLM-L6-v2** model.
- Tracks indexing state by updating the `ingestion_status` column in `all_data.xlsx` to prevent re-processing.

### 2. Research Chat (React View 1 & `backend.py`)
- Conversational chat powered by RAG and `gemini-2.5-flash`.
- Automatically applies any active filters from the sidebar to the vector database query scope.
- Displays cited sources with collapsible drawer lists.

### 3. Insight Engine (React View 2 & `insights.py`)
- Visualizes categories distribution (Pie/Donut), Narrative vs Official counts (Bar), and Growth Timeline (Line).
- Contains RAG-powered automated AI narratives interpreting each chart dynamically upon button click.

### 4. Document Explorer (React View 3)
- Features a real-time searchable grid using `@tanstack/react-virtual` to display 14,000+ files without lag.
- Includes filter dropdowns, export CSV capabilities, and a right-sliding sidebar drawer revealing raw document text.

### 5. Submit Experience (React View 4)
- Form containing validation alerts, AI categorization suggestions matching database classifications, and success confetti animations.

# Biblio AI — Hybrid Movie & Book Recommender

A conversational AI-powered recommender that suggests movies and books based on your taste. Built with Flask, NVIDIA LLaMA 4, TMDB, Open Library, and MySQL.

---

## Features

- **Conversational AI** — asks you 1–2 questions about your mood and taste before recommending
- **Movie enrichment** — pulls real posters, ratings, and TMDB detail links for every movie
- **Book enrichment** — pulls cover images and Open Library detail links for every book
- **Save favourites** — heart any recommendation to save it to your sidebar
- **Persistent sessions** — conversation history and favourites survive page refreshes and navigation
- **API Status page** — test all three external APIs at `/api-test` before running

---

## Project Structure

```
recommendation/
├── recommendation_app.py   # Flask backend — all routes, DB, and API logic
├── .env                    # Your secret API keys (never uploaded)
├── .env.example            # Safe template — shows what keys are needed
├── .gitignore              # Tells Git to ignore .env and cache files
├── README.md               # This file
└── templates/
    ├── index.html          # Main chat UI
    └── test_apis.html      # API status checker page
```

---

## Requirements

- Python 3.8+
- XAMPP (Apache + MySQL)
- A free TMDB account for the API key
- An NVIDIA API key (for LLaMA 4)

---

## Setup

### 1. Install Python dependencies

```bash
pip install flask flask-cors requests mysql-connector-python python-dotenv
```

### 2. Start XAMPP

Open the XAMPP Control Panel and start both **Apache** and **MySQL**.

### 3. Create the database

Open **phpMyAdmin** at `http://localhost/phpmyadmin` and create a new database named:

```
recommender_db
```

The app will create the required tables automatically on first run.

### 4. Set up your API keys

Copy the example file and fill in your real keys:

```bash
cp .env.example .env
```

Then open `.env` and replace the placeholders:

```env
NVIDIA_API_KEY=your_nvidia_key_here
TMDB_API_KEY=your_tmdb_read_access_token_here
DB_PASSWORD=
```

| Variable | Where to get it |
|---|---|
| `NVIDIA_API_KEY` | NVIDIA API portal |
| `TMDB_API_KEY` | themoviedb.org/settings/api → **API Read Access Token** (the long `eyJ...` token, not the short v3 key) |
| `DB_PASSWORD` | Your MySQL password — leave blank for XAMPP default |

> **Important:** The `.env` file is listed in `.gitignore` and will never be uploaded to GitHub. Never paste real keys directly into your Python code.

### 5. Run the app

```bash
python recommendation_app.py
```

### 6. Open in browser

| Page | URL |
|---|---|
| Chat | http://localhost:5002 |
| API Status | http://localhost:5002/api-test |

---

## Security — Keeping Keys Safe

This project uses `python-dotenv` to load secrets from a local `.env` file at runtime.

```
.env          ← your real keys — kept LOCAL, never uploaded
.env.example  ← a safe placeholder template — safe to upload
.gitignore    ← tells Git to ignore .env
```

**What each file does:**

- `.env` — loaded automatically when the app starts. Contains your real API keys. Git will never track this file.
- `.env.example` — a committed template with placeholder values so anyone cloning the repo knows what keys they need.
- `.gitignore` — prevents `.env`, `__pycache__`, and `.pyc` files from ever being committed.

If you clone this repo fresh, just run:

```bash
cp .env.example .env
# then fill in your real keys in .env
```

---

## How It Works

```
User message
    │
    ▼
Save to MySQL (sessions table)
    │
    ▼
Load full history → send to NVIDIA LLaMA 4
    │
    ▼
AI returns JSON  ──► still gathering info?  ──► follow-up question
    │                        │
    │                        ▼
    │               {message, recommendations: []}
    │
    ▼ recommendations ready
Enrich each item:
  movie → TMDB search (poster, rating, link)
  book  → Open Library search (cover, link)
    │
    ▼
Save enriched response to MySQL
    │
    ▼
Return to frontend → render cards
```

---

## API Routes

| Method | Route | Description |
|---|---|---|
| `GET` | `/` | Main chat page |
| `POST` | `/chat` | Send a message, get AI response |
| `GET` | `/history` | Load conversation history for a session |
| `POST` | `/clear` | Clear conversation history (keeps favourites) |
| `POST` | `/favourite` | Save a recommendation to favourites |
| `GET` | `/favourites` | Get all saved favourites for a session |
| `GET` | `/api-test` | API status checker page |
| `POST` | `/api-test/nvidia` | Test NVIDIA API connection |
| `POST` | `/api-test/tmdb` | Test TMDB API connection |
| `POST` | `/api-test/openlibrary` | Test Open Library connection |

---

## Database Tables

**`sessions`** — conversation history

| Column | Type | Description |
|---|---|---|
| id | INT | Auto-increment primary key |
| session | VARCHAR(100) | Session ID from the browser |
| role | VARCHAR(20) | `user` or `assistant` |
| content | TEXT | Message text or JSON response |
| created_at | DATETIME | Timestamp |

**`favourites`** — saved recommendations

| Column | Type | Description |
|---|---|---|
| id | INT | Auto-increment primary key |
| session | VARCHAR(100) | Session ID from the browser |
| category | VARCHAR(20) | `movie` or `book` |
| title | VARCHAR(255) | Title |
| creator | VARCHAR(255) | Director or author |
| poster_url | TEXT | Image URL |
| rating | FLOAT | TMDB rating (movies only) |
| detail_url | TEXT | Link to TMDB or Open Library |
| saved_at | DATETIME | Timestamp |

---

## Session Persistence

Each browser generates a unique session ID on first visit and stores it in `localStorage`. This means:

- Refreshing the page restores your full conversation and favourites
- Navigating away and coming back restores everything
- Clicking **New Chat** clears the conversation but **keeps your favourites**
- Different browsers or incognito windows start a fresh session

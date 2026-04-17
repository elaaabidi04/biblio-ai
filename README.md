# Biblio AI — Movie, TV Show & Book Recommender

A conversational AI-powered recommender that suggests movies, TV shows, and books based on your taste. Chat naturally, get personalized picks with real posters and ratings, and save your favourites.

**Live demo:** https://biblio-ai.onrender.com

---

## Author

**Elaa Aabidi** — sole author and developer.

### Tools used

| Tool | Role |
|---|---|
| [Claude (Anthropic)](https://claude.ai) | AI coding assistant — used throughout development |
| [Flora AI](https://floraai.com) | Logo generation |
| [Render](https://render.com) | Deployment and hosting |
| [Aiven](https://aiven.io) | Managed MySQL database (production) |
| [NVIDIA LLaMA 4](https://www.nvidia.com/en-us/ai/) | Recommendation AI model |
| [TMDB](https://www.themoviedb.org) | Movie and TV show posters, ratings, and links |
| [Open Library](https://openlibrary.org) | Book covers and detail links |

---

## Features

- **Conversational AI** — asks 1–2 questions about your mood and taste before recommending
- **Three categories** — movies, TV shows, and books, each visually distinct
- **Real posters & ratings** — pulled live from TMDB and Open Library
- **Save favourites** — save any recommendation to your sidebar with one click
- **Delete favourites** — remove saved items individually
- **Access lock** — 4 free messages, then a password is required to continue
- **Persistent sessions** — conversation history and favourites survive page refresh
- **Responsive design** — works on desktop and mobile
- **Resizable sidebar** — drag the sidebar edge to resize (desktop)

---

## Project Structure

```
recommendation/
├── recommendation_app.py   # Flask backend — all routes, DB, AI, and API logic
├── requirements.txt        # Python dependencies
├── ca.pem                  # Aiven SSL certificate (production)
├── .env                    # Your secret keys (never uploaded)
├── .env.example            # Safe template — copy this to .env
├── .gitignore              # Keeps .env and cache out of Git
├── README.md               # This file
├── static/
│   ├── logo.png            # Original logo (Flora AI)
│   └── favicon.png         # Cropped logo for navbar and browser tab
└── templates/
    ├── index.html          # Main chat UI
    └── test_apis.html      # API status checker page
```

---

## Requirements

- Python 3.8+
- A MySQL database (XAMPP locally, or Aiven for production)
- Free TMDB account → API Read Access Token
- NVIDIA API key (for LLaMA 4)

---

## Local Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

| Variable | Where to get it |
|---|---|
| `NVIDIA_API_KEY` | [NVIDIA API portal](https://developer.nvidia.com) |
| `TMDB_API_KEY` | [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api) — use the long `eyJ...` Read Access Token |
| `MYSQLPASSWORD` | Your MySQL root password (blank for XAMPP default) |
| `UNLOCK_PASSWORD` | Any password you want users to enter after 4 free messages |

> `.env` is in `.gitignore` and will never be committed to Git.

### 3. Start MySQL

**XAMPP:** Open the Control Panel and start MySQL.  
The app creates the required tables automatically on first run.

### 4. Run

```bash
python recommendation_app.py
```

Open http://localhost:5002

---

## Deploying to Render + Aiven

### 1. Create a free MySQL database on Aiven

1. Sign up at [aiven.io](https://aiven.io)
2. Create a **MySQL** service on the free plan
3. Download the **CA certificate** → save as `ca.pem` in the project root
4. Note your host, port, user, password, and database name

### 2. Set environment variables on Render

Go to your Render service → **Environment** and add:

| Key | Value |
|---|---|
| `MYSQLHOST` | Your Aiven host |
| `MYSQLPORT` | Your Aiven port (usually 5-digit, not 3306) |
| `MYSQLUSER` | `avnadmin` |
| `MYSQLPASSWORD` | Your Aiven password |
| `MYSQLDATABASE` | `defaultdb` |
| `MYSQL_SSL` | `true` |
| `MYSQL_SSL_CA` | `ca.pem` |
| `NVIDIA_API_KEY` | Your NVIDIA key |
| `TMDB_API_KEY` | Your TMDB token |
| `UNLOCK_PASSWORD` | Your chosen access password |

### 3. Set the start command on Render

```
gunicorn recommendation_app:app
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
    │
    ▼ recommendations ready
Enrich each item:
  movie  → TMDB /search/movie  (poster, rating, link)
  tvshow → TMDB /search/tv     (poster, rating, link)
  book   → Open Library search (cover, link)
    │
    ▼
Save enriched response to MySQL → return to frontend
```

---

## API Routes

| Method | Route | Description |
|---|---|---|
| `GET` | `/` | Main chat page |
| `POST` | `/chat` | Send a message, get AI response |
| `GET` | `/history` | Load conversation history |
| `POST` | `/clear` | Clear conversation (keeps favourites) |
| `POST` | `/favourite` | Save a recommendation |
| `GET` | `/favourites` | Get all saved favourites |
| `DELETE` | `/favourite/<id>` | Delete a saved favourite |
| `POST` | `/unlock` | Verify access password |
| `GET` | `/api-test` | API status checker page |

---

## Database Schema

**`sessions`** — conversation history

| Column | Type | Description |
|---|---|---|
| id | INT | Auto-increment primary key |
| session | VARCHAR(100) | Browser session ID |
| role | VARCHAR(20) | `user` or `assistant` |
| content | TEXT | Message text or JSON response |
| created_at | DATETIME | Timestamp |

**`favourites`** — saved recommendations

| Column | Type | Description |
|---|---|---|
| id | INT | Auto-increment primary key |
| session | VARCHAR(100) | Browser session ID |
| category | VARCHAR(20) | `movie`, `tvshow`, or `book` |
| title | VARCHAR(255) | Title |
| creator | VARCHAR(255) | Director, showrunner, or author |
| poster_url | TEXT | Image URL |
| rating | FLOAT | TMDB rating |
| detail_url | TEXT | Link to TMDB or Open Library |
| saved_at | DATETIME | Timestamp |

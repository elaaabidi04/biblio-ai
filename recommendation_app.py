"""
=======================================================
  HYBRID AI RECOMMENDER — Movies & Books
  Features:
    ✅ Conversational AI (asks follow-up questions)
    ✅ TMDB API for movie posters, ratings, watch links
    ✅ Open Library API for book covers, authors
    ✅ MySQL (XAMPP) for saving sessions & favourites
    ✅ NVIDIA LLaMA 4 for recommendations
=======================================================

SETUP STEPS:
  1. pip install flask flask-cors requests mysql-connector-python
  2. Start XAMPP → Start Apache + MySQL
  3. Open phpMyAdmin → create database called: recommender_db
  4. Set your API keys below or as environment variables:
       NVIDIA_API_KEY = your nvidia key
       TMDB_API_KEY   = get free key at https://www.themoviedb.org/settings/api
  5. python hybrid_recommender.py
  6. Open http://localhost:5002
"""

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import mysql.connector
import os
import json
import hmac
import hashlib
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ── CONFIG ──────────────────────────────────────────────────────────────────
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
TMDB_API_KEY   = os.environ.get("TMDB_API_KEY")

NVIDIA_URL     = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL          = "meta/llama-4-maverick-17b-128e-instruct"
TMDB_BASE      = "https://api.themoviedb.org/3"
TMDB_IMG       = "https://image.tmdb.org/t/p/w500"
OPEN_LIBRARY   = "https://openlibrary.org"

# ── MYSQL CONFIG ─────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.environ.get("MYSQLHOST",     "localhost"),
    "port":     int(os.environ.get("MYSQLPORT", "3306")),
    "user":     os.environ.get("MYSQLUSER",     "root"),
    "password": os.environ.get("MYSQLPASSWORD", ""),
    "database": os.environ.get("MYSQLDATABASE", "recommender_db"),
}
# Aiven requires SSL — only enabled when MYSQL_SSL=true is set
if os.environ.get("MYSQL_SSL", "").lower() == "true":
    DB_CONFIG["ssl_ca"] = os.environ.get("MYSQL_SSL_CA", "ca.pem")
# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE LAYER
# ══════════════════════════════════════════════════════════════════════════════

def get_db():
    """Returns a MySQL connection."""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Exception as e:
        raise ConnectionError(f"Database unavailable: {e}")


def make_unlock_token(session_id: str) -> str:
    pwd = os.environ.get("UNLOCK_PASSWORD", "")
    return hmac.new(pwd.encode(), session_id.encode(), hashlib.sha256).hexdigest()

def count_user_messages(session_id: str) -> int:
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM sessions WHERE session=%s AND role='user'", (session_id,))
    (n,) = cur.fetchone()
    cur.close()
    con.close()
    return n

def init_db():
    """
    Creates two tables if they don't exist:
      - sessions   : stores conversation history per user session
      - favourites : stores recommendations the user saved
    """
    con = get_db()
    cur = con.cursor()

    # Table 1: conversation history (same idea as your SQLite chat app)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id        INT AUTO_INCREMENT PRIMARY KEY,
            session   VARCHAR(100) NOT NULL,
            role      VARCHAR(20)  NOT NULL,
            content   TEXT         NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_session (session)
        )
    """)

    # Table 2: saved favourites
    cur.execute("""
        CREATE TABLE IF NOT EXISTS favourites (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            session    VARCHAR(100) NOT NULL,
            category   VARCHAR(20)  NOT NULL,
            title      VARCHAR(255) NOT NULL,
            creator    VARCHAR(255),
            poster_url TEXT,
            rating     FLOAT,
            detail_url TEXT,
            saved_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_session (session)
        )
    """)

    con.commit()
    cur.close()
    con.close()
    print("MySQL tables ready")


def get_history(session_id: str) -> list:
    """Loads full conversation history for a session."""
    con = get_db()
    cur = con.cursor()
    cur.execute(
        "SELECT role, content FROM sessions WHERE session=%s ORDER BY id ASC",
        (session_id,)
    )
    rows = cur.fetchall()
    cur.close()
    con.close()
    return [{"role": role, "content": content} for role, content in rows]


def save_message(session_id: str, role: str, content: str):
    """Saves a single message to the sessions table."""
    con = get_db()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO sessions (session, role, content) VALUES (%s, %s, %s)",
        (session_id, role, content)
    )
    con.commit()
    cur.close()
    con.close()


def clear_session(session_id: str):
    """Deletes all messages for a session."""
    con = get_db()
    cur = con.cursor()
    cur.execute("DELETE FROM sessions WHERE session=%s", (session_id,))
    con.commit()
    cur.close()
    con.close()


def save_favourite(session_id, category, title, creator, poster_url, rating, detail_url):
    """Saves a recommendation to the favourites table."""
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO favourites (session, category, title, creator, poster_url, rating, detail_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (session_id, category, title, creator, poster_url, rating, detail_url))
    con.commit()
    cur.close()
    con.close()


def get_favourites(session_id: str) -> list:
    """Returns all saved favourites for a session."""
    con = get_db()
    cur = con.cursor(dictionary=True)
    cur.execute(
        "SELECT * FROM favourites WHERE session=%s ORDER BY saved_at DESC",
        (session_id,)
    )
    rows = cur.fetchall()
    cur.close()
    con.close()
    return rows


# ══════════════════════════════════════════════════════════════════════════════
#  EXTERNAL API LAYER  (TMDB + Open Library)
# ══════════════════════════════════════════════════════════════════════════════

def enrich_movie(title: str) -> dict:
    """
    Searches TMDB for a movie by title.
    Returns poster URL, rating, and a TMDB detail link.
    """
    try:
        res = requests.get(
            f"{TMDB_BASE}/search/movie",
            headers={"Authorization": f"Bearer {TMDB_API_KEY}"},
            params={"query": title, "page": 1},
            timeout=10
        )
        results = res.json().get("results", [])
        if not results:
            return {}
        movie = results[0]
        poster = f"{TMDB_IMG}{movie['poster_path']}" if movie.get("poster_path") else None
        return {
            "poster_url": poster,
            "rating":     round(movie.get("vote_average", 0), 1),
            "detail_url": f"https://www.themoviedb.org/movie/{movie['id']}",
            "year":       movie.get("release_date", "")[:4]
        }
    except Exception as e:
        print(f"TMDB error for '{title}': {e}")
        return {}


def enrich_book(title: str, author: str = "") -> dict:
    """
    Searches Open Library for a book by title + author.
    Returns cover image URL and Open Library detail link.
    """
    try:
        query = f"{title} {author}".strip()
        res = requests.get(
            f"{OPEN_LIBRARY}/search.json",
            params={"q": query, "limit": 1},
            timeout=10
        )
        docs = res.json().get("docs", [])
        if not docs:
            return {}
        book = docs[0]
        cover_id = book.get("cover_i")
        cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None
        ol_key = book.get("key", "")
        return {
            "poster_url": cover_url,
            "rating":     None,
            "detail_url": f"https://openlibrary.org{ol_key}",
            "year":       str(book.get("first_publish_year", ""))
        }
    except Exception as e:
        print(f"Open Library error for '{title}': {e}")
        return {}


# ══════════════════════════════════════════════════════════════════════════════
#  AI LAYER  (Conversational + Structured output)
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are a friendly, expert media recommender for movies and books.

Your job is to have a SHORT conversation with the user to understand their taste,
then provide personalized recommendations.

CONVERSATION RULES:
- Start by asking 1-2 focused questions about their preferences (genre, mood, recent favourites).
- After 1-2 user replies, you have enough info — provide recommendations immediately.
- Do NOT keep asking questions forever. Recommend after gathering basic preferences.

WHEN RECOMMENDING, respond with ONLY a valid JSON object like this:
{
  "message": "Based on what you told me, here are my top picks for you!",
  "recommendations": [
    {
      "title":    "Movie or Book title",
      "creator":  "Director or Author name",
      "category": "movie" or "book",
      "why":      "One sentence why this matches their taste",
      "mood":     "One word vibe (e.g. thrilling, cozy, epic)"
    }
  ]
}

WHEN STILL GATHERING INFO (no recommendations yet), respond with ONLY:
{
  "message": "Your follow-up question here",
  "recommendations": []
}

IMPORTANT:
- Always return valid JSON, nothing else.
- Mix movies AND books in recommendations unless user specifies one.
- Provide exactly 3 recommendations when ready.
- Keep messages warm and conversational.
"""


def call_ai(history: list) -> dict:
    """
    Sends conversation history to the AI.
    Returns parsed JSON with 'message' and 'recommendations'.
    """
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Accept": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + history,
        "max_tokens": 800,
        "temperature": 0.75,
        "stream": False
    }

    resp = requests.post(NVIDIA_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]

    # Strip markdown fences if AI wraps in ```json
    clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(clean)


# ══════════════════════════════════════════════════════════════════════════════
#  FLASK ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api-test")
def api_test_page():
    return render_template("test_apis.html")


@app.route("/api-test/nvidia", methods=["POST"])
def api_test_nvidia():
    """Tests the NVIDIA API with a minimal prompt."""
    try:
        headers = {
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Accept": "application/json"
        }
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": "Reply with only the word: OK"}],
            "max_tokens": 10,
            "temperature": 0,
            "stream": False
        }
        resp = requests.post(NVIDIA_URL, headers=headers, json=payload, timeout=20)
        reply = resp.json()["choices"][0]["message"]["content"].strip()
        return jsonify({
            "ok": True,
            "status_code": resp.status_code,
            "model": MODEL,
            "reply_preview": reply[:80]
        })
    except requests.exceptions.HTTPError as e:
        return jsonify({"ok": False, "status_code": e.response.status_code if e.response else None, "error": str(e)})
    except Exception as e:
        return jsonify({"ok": False, "status_code": None, "error": str(e)})


@app.route("/api-test/tmdb", methods=["POST"])
def api_test_tmdb():
    """Tests the TMDB API by searching for a known movie."""
    try:
        resp = requests.get(
            f"{TMDB_BASE}/search/movie",
            headers={"Authorization": f"Bearer {TMDB_API_KEY}"},
            params={"query": "Inception", "page": 1},
            timeout=10
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return jsonify({"ok": False, "status_code": resp.status_code, "error": "No results returned"})
        movie = results[0]
        return jsonify({
            "ok": True,
            "status_code": resp.status_code,
            "sample_title": movie.get("title", ""),
            "has_poster": bool(movie.get("poster_path")),
            "rating": round(movie.get("vote_average", 0), 1)
        })
    except requests.exceptions.HTTPError as e:
        return jsonify({"ok": False, "status_code": e.response.status_code if e.response else None, "error": str(e)})
    except Exception as e:
        return jsonify({"ok": False, "status_code": None, "error": str(e)})


@app.route("/api-test/openlibrary", methods=["POST"])
def api_test_openlibrary():
    """Tests the Open Library API by searching for a known book."""
    try:
        resp = requests.get(
            f"{OPEN_LIBRARY}/search.json",
            params={"q": "Dune Frank Herbert", "limit": 1},
            timeout=10
        )
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
        if not docs:
            return jsonify({"ok": False, "status_code": resp.status_code, "error": "No results returned"})
        book = docs[0]
        return jsonify({
            "ok": True,
            "status_code": resp.status_code,
            "sample_title": book.get("title", ""),
            "has_cover": bool(book.get("cover_i")),
            "year": str(book.get("first_publish_year", ""))
        })
    except requests.exceptions.HTTPError as e:
        return jsonify({"ok": False, "status_code": e.response.status_code if e.response else None, "error": str(e)})
    except Exception as e:
        return jsonify({"ok": False, "status_code": None, "error": str(e)})


@app.route("/unlock", methods=["POST"])
def unlock():
    data       = request.get_json() or {}
    password   = data.get("password", "")
    session_id = data.get("session_id", "default")
    expected   = os.environ.get("UNLOCK_PASSWORD", "")
    if expected and password == expected:
        return jsonify({"ok": True, "token": make_unlock_token(session_id)})
    return jsonify({"ok": False, "error": "Wrong password"}), 401


@app.route("/history", methods=["GET"])
def history():
    """Returns the conversation history for a session, ready to render."""
    session_id = request.args.get("session_id", "default")
    try:
        rows = get_history(session_id)
    except Exception:
        return jsonify({"messages": []})
    messages = []
    for row in rows:
        if row["role"] == "user":
            messages.append({"role": "user", "content": row["content"]})
        elif row["role"] == "assistant":
            try:
                parsed = json.loads(row["content"])
                messages.append({
                    "role": "assistant",
                    "message": parsed.get("message", ""),
                    "recommendations": parsed.get("recommendations", [])
                })
            except (json.JSONDecodeError, TypeError):
                messages.append({"role": "assistant", "message": row["content"], "recommendations": []})
    return jsonify({"messages": messages})


@app.route("/chat", methods=["POST"])
def chat():
    """
    Main conversational endpoint.
    POST body: { "message": "...", "session_id": "..." }

    Flow:
      1. Save user message to MySQL
      2. Load full history from MySQL
      3. Send history to AI
      4. If AI returns recommendations → enrich with TMDB / Open Library
      5. Save AI reply to MySQL
      6. Return response to frontend
    """
    data       = request.get_json()
    user_msg   = data.get("message", "").strip()
    session_id = data.get("session_id", "default")

    if not user_msg:
        return jsonify({"error": "Empty message"}), 400

    # Enforce 1-message limit for locked sessions
    unlock_token = request.headers.get("X-Unlock-Token", "")
    if unlock_token != make_unlock_token(session_id):
        try:
            if count_user_messages(session_id) >= 4:
                return jsonify({"error": "locked"}), 403
        except Exception:
            pass  # if DB is down, allow the message

    # 1. Save user message
    try:
        save_message(session_id, "user", user_msg)
    except Exception:
        pass  # continue even if DB is down

    # 2. Load full history
    try:
        history = get_history(session_id)
    except Exception:
        history = []

    # 3. Call AI
    try:
        ai_response = call_ai(history)
    except json.JSONDecodeError:
        return jsonify({"error": "AI returned unexpected format. Try again."}), 500
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"AI API error: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"AI error: {e}"}), 500

    message         = ai_response.get("message", "")
    recommendations = ai_response.get("recommendations", [])

    # 4. Enrich recommendations with real data
    enriched = []
    for rec in recommendations:
        extra = {}
        if rec.get("category") == "movie":
            extra = enrich_movie(rec["title"])
        elif rec.get("category") == "book":
            extra = enrich_book(rec["title"], rec.get("creator", ""))
        enriched.append({**rec, **extra})

    # 5. Save AI reply to MySQL (save enriched so posters/ratings survive restore)
    save_message(session_id, "assistant", json.dumps({"message": message, "recommendations": enriched}))

    return jsonify({
        "message":         message,
        "recommendations": enriched
    })


@app.route("/favourite", methods=["POST"])
def favourite():
    """Saves a recommendation to the favourites table."""
    data = request.get_json()
    try:
        save_favourite(
            session_id = data.get("session_id", "default"),
            category   = data.get("category", ""),
            title      = data.get("title", ""),
            creator    = data.get("creator", ""),
            poster_url = data.get("poster_url", ""),
            rating     = data.get("rating"),
            detail_url = data.get("detail_url", "")
        )
        return jsonify({"status": "saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/favourites", methods=["GET"])
def favourites():
    """Returns all saved favourites for a session."""
    session_id = request.args.get("session_id", "default")
    return jsonify({"favourites": get_favourites(session_id)})


@app.route("/favourite/<int:fav_id>", methods=["DELETE"])
def delete_favourite(fav_id):
    session_id = request.args.get("session_id", "default")
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute("DELETE FROM favourites WHERE id=%s AND session=%s", (fav_id, session_id))
        con.commit()
        cur.close()
        con.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/clear", methods=["POST"])
def clear():
    """Clears a session's conversation history."""
    session_id = request.get_json().get("session_id", "default")
    clear_session(session_id)
    return jsonify({"status": "cleared"})



# ── ENTRY POINT ──────────────────────────────────────────────────────────────
try:
    init_db()
    print("MySQL tables ready")
except Exception as e:
    print(f"WARNING: Could not init database: {e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port)
from flask import Flask, render_template, request, jsonify, Response
import requests
import json
import subprocess
import sqlite3
import uuid
from datetime import datetime
import os
import threading

app = Flask(__name__)

OLLAMA_URL = "http://localhost:11434/api/chat"
DB_PATH = os.path.expanduser("~/ai-assistant/memory.db")

MODELS = {
    "assistant": "llama3",
    "coder": "qwen2.5-coder",
    "memory": "llama3"
}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT,
            last_active TEXT,
            title TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            mode TEXT,
            timestamp TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT UNIQUE,
            source TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_all_memories():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, content, source, created_at FROM memories ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [{"id": row["id"], "content": row["content"], "source": row["source"], "created_at": row["created_at"]} for row in rows]

def save_memory(content, source="auto"):
    conn = get_db()
    now = datetime.now().isoformat()
    try:
        conn.execute(
            "INSERT INTO memories (content, source, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (content.strip(), source, now, now)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def delete_memory(memory_id):
    conn = get_db()
    conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
    conn.commit()
    conn.close()

def update_memory(memory_id, content):
    conn = get_db()
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE memories SET content=?, updated_at=? WHERE id=?",
        (content.strip(), now, memory_id)
    )
    conn.commit()
    conn.close()

def build_memory_context():
    memories = get_all_memories()
    if not memories:
        return ""
    facts = "\n".join([f"- {m['content']}" for m in memories])
    return f"\n\nWhat you know about the user:\n{facts}\n"

def extract_memories_from_conversation(session_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE session_id=? ORDER BY id ASC",
        (session_id,)
    ).fetchall()
    conn.close()

    if len(rows) < 2:
        return

    conversation = "\n".join([f"{r['role'].upper()}: {r['content']}" for r in rows])

    prompt = f"""Read this conversation and extract specific facts about the user worth remembering long term.

Focus on: job, skills, tools, projects, preferences, goals, personal context.

Rules:
- Only extract clear facts, not guesses
- Each fact is one short sentence
- Return ONLY a JSON array like this: ["fact one", "fact two"]
- If nothing is worth remembering return: []
- Do not add any explanation or text outside the JSON array

Conversation:
{conversation}

JSON array (only, nothing else):"""

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODELS["memory"],
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0}
        }, timeout=60)

        result = response.json()
        text = result["message"]["content"].strip()

        # Try to find JSON array anywhere in the response
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            return

        text = text[start:end+1]
        facts = json.loads(text)

        for fact in facts:
            if isinstance(fact, str) and len(fact) > 5:
                save_memory(fact, source="auto")

    except Exception as e:
        print(f"Memory extraction error: {e}")
def create_session():
    conn = get_db()
    session_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO sessions (id, created_at, last_active, title) VALUES (?, ?, ?, ?)",
        (session_id, now, now, "New Chat")
    )
    conn.commit()
    conn.close()
    return session_id

def save_message(session_id, role, content, mode):
    conn = get_db()
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO messages (session_id, role, content, mode, timestamp) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, mode, now)
    )
    conn.execute("UPDATE sessions SET last_active=? WHERE id=?", (now, session_id))
    count = conn.execute(
        "SELECT COUNT(*) as c FROM messages WHERE session_id=? AND role='user'",
        (session_id,)
    ).fetchone()["c"]
    if count == 1 and role == "user":
        title = content[:40] + "..." if len(content) > 40 else content
        conn.execute("UPDATE sessions SET title=? WHERE id=?", (title, session_id))
    conn.commit()
    conn.close()

def load_session_messages(session_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE session_id=? ORDER BY id ASC",
        (session_id,)
    ).fetchall()
    conn.close()
    return [{"role": row["role"], "content": row["content"]} for row in rows]

def get_all_sessions():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, last_active FROM sessions ORDER BY last_active DESC"
    ).fetchall()
    conn.close()
    return [{"id": row["id"], "title": row["title"], "last_active": row["last_active"]} for row in rows]

def get_latest_session():
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM sessions ORDER BY last_active DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["id"] if row else None

current_session_id = None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/init", methods=["GET"])
def init_session():
    global current_session_id
    session_id = get_latest_session()
    if not session_id:
        session_id = create_session()
    current_session_id = session_id
    messages = load_session_messages(session_id)
    sessions = get_all_sessions()
    memories = get_all_memories()
    return jsonify({
        "session_id": session_id,
        "messages": messages,
        "sessions": sessions,
        "memories": memories
    })

@app.route("/new_session", methods=["POST"])
def new_session():
    global current_session_id
    session_id = create_session()
    current_session_id = session_id
    sessions = get_all_sessions()
    return jsonify({"session_id": session_id, "sessions": sessions})

@app.route("/load_session", methods=["POST"])
def load_session():
    global current_session_id
    data = request.json
    session_id = data.get("session_id")
    current_session_id = session_id
    messages = load_session_messages(session_id)
    return jsonify({"session_id": session_id, "messages": messages})

@app.route("/chat", methods=["POST"])
def chat():
    global current_session_id
    data = request.json
    message = data.get("message", "")
    mode = data.get("mode", "assistant")

    if message.lower().startswith("remember "):
        fact = message[9:].strip()
        save_memory(fact, source="manual")
        def ack():
            yield f"data: {json.dumps({'token': 'Got it, I will remember that: ' + fact})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        save_message(current_session_id, "user", message, mode)
        save_message(current_session_id, "assistant", "Got it, I will remember that: " + fact, mode)
        return Response(ack(), mimetype="text/event-stream")

    if message.lower().startswith("forget "):
        fact = message[7:].strip()
        conn = get_db()
        conn.execute("DELETE FROM memories WHERE content LIKE ?", (f"%{fact}%",))
        conn.commit()
        conn.close()
        def ack():
            yield f"data: {json.dumps({'token': 'Done, removed any memories matching: ' + fact})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        save_message(current_session_id, "user", message, mode)
        save_message(current_session_id, "assistant", "Done, removed any memories matching: " + fact, mode)
        return Response(ack(), mimetype="text/event-stream")

    if not current_session_id:
        current_session_id = create_session()

    save_message(current_session_id, "user", message, mode)
    history = load_session_messages(current_session_id)
    memory_context = build_memory_context()

    system_prompts = {
        "assistant": "You are a helpful assistant. Be concise and clear." + memory_context,
        "coder": "You are an expert coding assistant. When providing code, always explain what it does. Use best practices." + memory_context
    }

    payload = {
        "model": MODELS.get(mode, MODELS["assistant"]),
        "messages": [
            {"role": "system", "content": system_prompts[mode]}
        ] + history,
        "stream": True
    }

    def generate():
        full_response = ""
        response = requests.post(OLLAMA_URL, json=payload, stream=True)
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line)
                if "message" in chunk:
                    token = chunk["message"].get("content", "")
                    full_response += token
                    yield f"data: {json.dumps({'token': token})}\n\n"
                if chunk.get("done"):
                    save_message(current_session_id, "assistant", full_response, mode)
                    t = threading.Thread(
                        target=extract_memories_from_conversation,
                        args=(current_session_id,)
                    )
                    t.daemon = True
                    t.start()
                    yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(generate(), mimetype="text/event-stream")

@app.route("/memories", methods=["GET"])
def memories():
    return jsonify(get_all_memories())

@app.route("/memory/add", methods=["POST"])
def memory_add():
    data = request.json
    save_memory(data.get("content", ""), source="manual")
    return jsonify(get_all_memories())

@app.route("/memory/delete", methods=["POST"])
def memory_delete():
    data = request.json
    delete_memory(data.get("id"))
    return jsonify(get_all_memories())

@app.route("/memory/update", methods=["POST"])
def memory_update():
    data = request.json
    update_memory(data.get("id"), data.get("content"))
    return jsonify(get_all_memories())

@app.route("/run_code", methods=["POST"])
def run_code():
    data = request.json
    code = data.get("code", "")
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout or result.stderr
    except subprocess.TimeoutExpired:
        output = "Error: Code execution timed out (10s limit)"
    except Exception as e:
        output = f"Error: {str(e)}"
    return jsonify({"output": output})

if __name__ == "__main__":
    init_db()
    print("Database initialized at", DB_PATH)
    app.run(debug=True, port=5000)

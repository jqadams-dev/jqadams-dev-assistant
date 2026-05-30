# Local AI Assistant

A fully local AI assistant and coding helper that runs on your machine. No cloud, no API keys, no data leaving your machine.

Built with Python, Flask, and Ollama.

## Features

- **Assistant mode** — general purpose chat using llama3
- **Coder mode** — coding help using qwen2.5-coder
- **Run code** — execute Python code blocks directly from the UI
- **Persistent memory** — remembers facts about you across sessions automatically
- **Chat history** — all conversations saved locally in SQLite
- **Manual memory** — add, edit, or delete what it knows about you

## Requirements

- macOS or Linux
- Python 3.9+
- [Ollama](https://ollama.com) installed and running

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/yourusername/ai-assistant.git
cd ai-assistant
```

**2. Create a virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install flask requests flask-sqlalchemy
```

**4. Pull the required models**
```bash
ollama pull llama3
ollama pull qwen2.5-coder
```

**5. Run the app**
```bash
python3 app.py
```

**6. Open your browser**
```
http://127.0.0.1:5000
```

## Usage

- Type a message and hit Enter or click Send
- Switch between **Assistant** and **Coder** modes using the buttons in the header
- Click **Memory** in the sidebar to see what the AI has learned about you
- Type `remember [fact]` to manually save something
- Type `forget [topic]` to remove a memory
- Click **+ New** in the sidebar to start a fresh chat session

## Project Structure

```
ai-assistant/
├── app.py              # Flask backend
├── templates/
│   └── index.html      # Web UI
├── memory.db           # SQLite database (auto-created)
└── venv/               # Python virtual environment
```

## Notes

- All data is stored locally in `memory.db`
- The app runs in debug mode by default — fine for local use
- Memory extraction runs in the background after each response using llama3

# Async AI Agent

Async is a high-performance, OS-level desktop AI agent built for seamless task orchestration. It features a hardened Electron frontend and a sophisticated Python-based "State Core" backend.

## Features

- **Multi-step Planning:** Intelligent task decomposition using Gemini 2.0.
- **Closed-Loop Intelligence:** deterministic element targeting using ARIA/Accessibility references.
- **Human-Mode Simulation:** Natural Bezier-curve mouse movements and variable typing speeds.
- **Persistent Memory:** SQLite-backed state and skill workshop that survives reboots.
- **Global Hotkey:** `Windows + J` to toggle the command center instantly.
- **Proactive Scheduling:** Background job management for recurring tasks.
- **Aeruk Design Aesthetic:** Premium glassmorphic UI with real-time system logs.

## Setup & Running

### Prerequisites
- Node.js (v18+)
- Python 3.10+
- Google Gemini API Key

### Installation

1. **Install Node dependencies:**
   ```bash
   npm install
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright Browsers:**
   ```bash
   playwright install chromium
   ```

### Running the App

1. **Start the application:**
   ```bash
   npm start
   ```

### Packaging as .exe (Windows)

To build a standalone portable executable:
```bash
npm run dist
```
The output will be in the `dist/` folder.

2. **Configure:**
   - Use `Windows + J` to open the Async panel.
   - Click **SETTINGS** and enter your **Gemini API Key**.
   - Toggle **HUMAN MODE** if you want stealthy, human-like interactions.

3. **Execute:**
   - Type a task in the command surface (e.g., "Open Excel and make a table of my expenses") and hit **EXECUTE**.

## Architecture

Async follows a strict **Plan -> Bind -> Observe -> Execute -> Verify -> Recover** lifecycle.

- **Frontend:** Electron + Vanilla JS (Hardened with contextIsolation).
- **Backend:** Python (asyncio) + SQLite.
- **Orchestration:** `AgentRuntime` manages the lifecycle between vision, planning, and execution.
- **Safety:** Enforces "No-State-No-Action" rules and UI stabilization gates.

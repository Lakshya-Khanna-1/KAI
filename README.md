# KAI — Personal AI Assistant

A self-hosted, private, Jarvis-style personal AI assistant running locally on home server infrastructure.

## Setup Instructions

1. **Clone Repository & Enter Directory**
   ```bash
   cd KAI
   ```

2. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env to customize KAI_OWNER_NAME and Ollama URL if needed
   ```

3. **Ensure Ollama is Running**
   Ensure Ollama is running locally with the target model (`qwen3:8b`).

4. **Run with Docker Compose**
   ```bash
   docker compose up -d
   ```

5. **Verify System Health**
   Access `http://localhost:8000/health` or curl:
   ```bash
   curl http://localhost:8000/health
   ```

6. **Run Test Suite (Local Python Environment)**
   ```bash
   pytest
   ```

## Features Complete in V1 Framework (Tasks 1-15)
- Fully offline native LLM operations via local Ollama
- Full-duplex Voice Interaction Mode using `whisper.cpp` & Piper TTS
- PWA Mobile Frontend (accessible on-the-go via Tailscale)
- RAG "Permanent Memory" vector store via Qdrant
- Gym & Progressive Overload Tracking with automatic PB notifications
- Live dynamic web searching capabilities and Roadmap planning tools
- Intelligent background scheduler + automated task completion

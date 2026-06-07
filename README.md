# AI-STORY-ADVENTURE - Backend Engine

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/Framework-FastAPI-009688.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/Database-SQLite%20(WAL)-blue" alt="SQLite">
  <img src="https://img.shields.io/badge/VectorDB-FAISS-ff69b4.svg" alt="FAISS">
  <img src="https://img.shields.io/badge/AI-Groq%20%7C%20Gemini%20%7C%20Ollama-orange" alt="LLMs">
</p>

**AI STORY ADVENTURE** is a Text-based RPG Game Engine driven entirely by Artificial Intelligence. The backend is built upon a strict, modular framework (Clean Architecture), integrating RAG (Retrieval-Augmented Generation) to create long-term memory, alongside a complex Prompt Engineering system to coordinate multiple AI Agents (Game Master, Entity Extractor, Quest Judge, etc.).

The system provides a high-speed RESTful API via FastAPI, designed for seamless integration with Frontends (such as Unity).

---

## ✨ Key Features

* 🧠 **Multi-Agent System:** * Utilizes multiple LLMs simultaneously (Llama-3 via Groq for high-speed inference, Gemini for complex logic tasks, Ollama for offline processing).
    * Clear role separation: `StoryAgent` for narration, `StateExtractor` for tracking context, and `ItemAgent` for physics/logic arbitration.
* 📚 **Hybrid RAG Memory System:**
    * **Short-term:** A Sliding Window of the 4 most recent turns.
    * **Long-term:** Vector storage using `FAISS` and `SentenceTransformers` combined with a Custom Reranking algorithm (Time Decay + Keyword Exact Match).
    * **Personal History:** Ultra-fast SQLite queries to retrieve separate, isolated interaction histories for each NPC.
* 🎒 **Inventory & Stats Management:**
    * Real-time damage/defense calculation via `StatsManager`.
    * Handles creative crafting and item usage logic strictly refereed by AI through the `ItemProcessor`.
* 🗺️ **Dynamic World & Quests:**
    * Auto-generates images (Backgrounds, NPCs, Items) via the SDXL API with a smart local caching mechanism (`ImageManager`).
    * Flexible Quest Management system (`QuestProcessor`), allowing dynamic target switching and automated background progress evaluation.
* ⚡ **High Performance:**
    * Asynchronous I/O processing using `aiosqlite` (WAL mode) and `FastAPI Background Tasks` ensuring zero-blocking responses for players.

---

## 🏗️ System Architecture

The project strictly adheres to **SOLID** principles and is separated into distinct layers:

```text
Eldoria/
├── engine/
│   ├── Agents/          # Classes calling LLM APIs (CloudAgents, LocalAgents)
│   ├── DataManager/     # DAO/Repository Pattern managing DB (SQLite + FAISS), State, Inventory
│   ├── Subengine/       # Business Logic Layer (ActionProcessor, MemoryProcessor, QuestProcessor)
│   ├── Utils/           # Utilities (PromptManager, TextFormatter, Logger, Audio)
│   ├── ImageAPI.py      # Connection to Kaggle SDXL for image generation
│   └── Orchestration.py # Facade Pattern: The conductor coordinating the entire system
├── world/
│   └── Entity.py        # Dataclasses & OOP Models (NPC, Location, Item, Memory, Quest)
├── static/
│   └── prompts.yaml     # The heart of the AI - Manages all dynamic prompts
├── server.py            # FastAPI Entry point, defining Endpoints
└── tests/               # Unit testing (Pytest)
```

### 3. Environment Variables
Create a `.env` file in the `SaveData` directory (or root directory) with the following content:
```env
GROQ_API_KEY=your_groq_key_here
GEMINI_API_KEY=your_gemini_key_here


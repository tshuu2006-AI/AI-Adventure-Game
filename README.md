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
```
## 📡 Core API Endpoints

**Core Gameplay & Loop**
* `POST /api/new_game`: Initializes the context, world bible, and starting state from a text-based idea.
* `POST /api/play`: Receives player actions, retrieves RAG context, generates story responses, and triggers Background Tasks (State Extraction, Memory Save).
* `GET /api/poll_updates`: Returns real-time state data (HP, Inventory, Image Base64, Active Quest) to the Client independently of the chat flow.

**System & Settings**
* `GET /api/ping`: Endpoint called continuously by Unity to verify if the server is fully initialized and ready.
* `POST /api/shutdown`: Safely terminates the FastAPI server when the Unity application closes.
* `POST /api/check_config`: Validates Cloud (Groq) and Local (Gemini/Ollama) API Key configurations from the Unity Menu.
* `POST /api/settings`: Dynamically updates game settings (AI Model switching, Image Quality, and Image Generation toggles).
* `GET /api/progress`: Allows the frontend to fetch loading progress percentages and messages during heavy background processing.

**Data & Save Management**
* `POST /api/save_game` | `/api/load_game`: Manages saving/restoring the entire SQLite DB and FAISS memory to/from physical storage.
* `POST /api/delete_save`: Completely deletes a designated save slot, removing associated image directories and JSON configuration files.
* `GET /api/diary`: Retrieves the comprehensive database of all encountered NPCs, Locations, and active/completed Quests.

**Quest & Inventory Systems**
* `POST /api/quest/switch`: Switches the currently tracked Active Quest and dynamically generates a narrative transition text.
* `POST /api/inventory/use`: Handles item consumption or creative usage relying strictly on AI logic evaluation.
* `POST /api/inventory/craft`: Combines physical items based on AI logic evaluation.
* `POST /api/inventory/equip`: Equips a specified weapon from the player's inventory.
* `POST /api/inventory/unequip`: Unequips the currently active weapon, returning the character to an unarmed state.

## 🚀 MVP Quick Start Guide

Experience the **AI Story Adventure** MVP instantly! The provided build is fully standalone and pre-configured (bundling both the backend engine and the Unity frontend). There is no need to install Python or set up virtual environments—just download, click, and play.

### 1. Download the Game
Download the complete MVP package from our Google Drive:
* 📁 **[Download Eldoria MVP here](https://drive.google.com/drive/folders/1_2t_fb7WJP2B2Loi0hjlqqj57EM_xpYA?usp=sharing)** * *Note: Extract the downloaded `.zip` or `.rar` file to an empty folder on your computer.*
### 2. Configure Your AI Engine
Since AI Story Adventure is driven by live AI models, you need to set up your AI providers to bring the world to life. 

**Step A: Get your Cloud API Key (Required for High-Speed Generation)**
* 🔑 **[Get Groq API Key](https://console.groq.com/keys)** (Requires a free GroqCloud account)

**Step B: Setup your Logic AI Engine (Choose Option 1 OR Option 2)**
AI Story Adventure uses a secondary AI for complex game logic and physics arbitration. You can either use a cloud-based API or run it completely offline on your own hardware.

**Option 1: Use Gemini API (Cloud - Recommended for ease of use)**
1. 🔑 **[Get Gemini API Key](https://aistudio.google.com/app/apikey)** (Requires a free Google account).
**Option 2: Setup Local AI via Ollama (Offline Processing)**
If you prefer to run the game's logic entirely locally on your machine instead of using cloud keys like Gemini:
1. **Install the Engine:** Download and install [Ollama](https://ollama.com) for your system.
2. **Keep it Running:** Ensure the Ollama application is active and running in the background before launching the game.
*(Tip: You can easily toggle between Gemini API models and Local Ollama models directly through the in-game Settings Menu!)*

**Step C: Setup Image Generation via Kaggle SDXL (Optional)**
Eldoria can dynamically generate visual representations of locations, NPCs, and items. You can host your own high-speed image generation server for free using Kaggle.

1. **Import the Notebook:** Log in to Kaggle, create a **New Notebook**, and select **File -> Import Notebook** to upload the provided `imagegenerator.ipynb` file.
2. **Enable Hardware & Internet:** In the right-hand panel (Session Options) of your Kaggle environment, ensure that **Internet** is turned ON and the **GPU** accelerator (e.g., NVIDIA Tesla T4) is selected.
3. **Run the Cells in strict order:**
   * **Run Cell 1:** Execute the first cell to install all required core libraries.
   * **Restart Session:** Click the three dots menu at the top and select **Restart & Clear Cell Outputs** to refresh the environment.
   * **Run Cell 1 Again:** Re-run the first cell to ensure all dependencies are properly loaded.
   * **Run Cell 2:** Execute the second cell (the server code). Wait for the model to load into the GPUs.


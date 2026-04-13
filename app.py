from engine.Orchestration import GameOrchestrator
from dotenv import load_dotenv
import os
import asyncio

if __name__ == "__main__":
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    orchestrator = GameOrchestrator(db_path="./data/World.db", vector_model_path="all-MiniLM-L6-v2", groq_api_key=api_key)
    asyncio.run(orchestrator.run())
    

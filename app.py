from engine.Orchestration import GameOrchestrator
from dotenv import load_dotenv
import os
import asyncio

if __name__ == "__main__":
    load_dotenv()
    groq_api_key = os.getenv("GROQ_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    orchestrator = GameOrchestrator(db_path="./data/World.db",
                                    vector_model_path="bkai-foundation-models/vietnamese-bi-encoder",
                                    groq_api_key=groq_api_key,
                                    gemini_api_key = gemini_api_key)
    asyncio.run(orchestrator.run())
    

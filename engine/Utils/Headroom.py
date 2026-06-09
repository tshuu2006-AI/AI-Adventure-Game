import re
from typing import Dict, Tuple

class HeadroomOptimizer:
    """
    Headroom-inspired context optimizer for AI-Adventure-Game.
    Provides context compression, prompt stabilization, and CCR (Compress-Cache-Retrieve) cache.
    """
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.ccr_cache: Dict[str, str] = {}
        self.cache_counter = 0
        
        # Statistics
        self.total_raw_chars = 0
        self.total_compressed_chars = 0
        
        # Vietnamese stop words to filter out from verbose RAG memory if needed
        # We only remove very common low-semantic noise words in memories to avoid losing plot details.
        self.stop_words = ["thì", "là", "mà", "cái", "chiếc", "những"]

    def register_in_ccr(self, original_text: str) -> str:
        """Saves original text to local cache and returns a short reference ID."""
        self.cache_counter += 1
        ref_id = f"ref_{self.cache_counter}"
        self.ccr_cache[ref_id] = original_text
        return ref_id

    def retrieve_original(self, ref_id: str) -> str:
        """Retrieves original uncompressed text from cache."""
        return self.ccr_cache.get(ref_id, "[Không tìm thấy dữ liệu gốc]")

    def compress_rag_context(self, raw_context: str) -> str:
        """
        Compresses the hybrid RAG context by:
        1. Shrinking headers and prefix tags.
        2. Removing redundant spaces, empty lines, and specific stop words.
        3. Storing large texts in CCR cache and referencing them.
        """
        if not self.enabled or not raw_context:
            return raw_context

        self.total_raw_chars += len(raw_context)

        # Step 1: Abbreviations for headers and structures
        compressed = raw_context
        
        # First compress the FAISS turn info: - (Turn X tại Y): -> - TX @ Y:
        compressed = re.sub(r'- \(Turn (\d+) tại ([^)]+)\):', r'- T\1 @ \2:', compressed)

        # Header mappings
        mappings = {
            "[BỐI CẢNH HIỆN TẠI]": "[CURR_CTX]",
            "- Địa điểm:": "@Loc:",
            "- Quá khứ gần:": "Past:",
            "- Player đang làm:": "Act:",
            "[LỊCH SỬ CÁ NHÂN VỚI NPC]": "[NPC_HIST]",
            "Lịch sử với ": "w/ ",
            "[CÁC KÝ ỨC MÔI TRƯỜNG KHÁC (TỪ FAISS)]": "[FAISS_MEM]",
        }
        
        for k, v in mappings.items():
            compressed = compressed.replace(k, v)

        # Step 2: Content contractions to save tokens without losing semantics
        contractions = {
            "người chơi": "player",
            "Người chơi": "player",
            "nhân vật": "npc",
            "Nhân vật": "npc",
            "trận chiến": "combat",
            "Trận chiến": "combat",
            "vũ khí": "weapon",
            "Vũ khí": "weapon",
            "sát thương": "dmg",
            "Sát thương": "dmg",
            "máu": "HP",
            "Máu": "HP",
            "không có": "ko",
            "Không có": "Ko",
        }
        for k, v in contractions.items():
            compressed = compressed.replace(k, v)

        # Step 3: Remove double spaces and clean up newlines
        lines = []
        for line in compressed.split("\n"):
            line = line.strip()
            if not line:
                continue
            
            # Simple word-level filtering for overly verbose memories (only in memory section)
            # If the line contains a memory text, we can do light stop word filtering.
            if line.startswith("-") or line.startswith("*"):
                words = line.split()
                filtered_words = [w for w in words if w.lower() not in self.stop_words]
                line = " ".join(filtered_words)
                
            lines.append(line)
            
        compressed = "\n".join(lines)
        self.total_compressed_chars += len(compressed)

        return compressed

    def get_stats(self) -> Dict[str, any]:
        """Returns optimization statistics."""
        saving_chars = self.total_raw_chars - self.total_compressed_chars
        pct = (saving_chars / self.total_raw_chars * 100) if self.total_raw_chars > 0 else 0
        
        # Estimate tokens (approx 3 characters per token in Vietnamese/English mixed texts)
        est_raw_tokens = int(self.total_raw_chars / 3)
        est_comp_tokens = int(self.total_compressed_chars / 3)
        est_token_savings = est_raw_tokens - est_comp_tokens
        
        return {
            "raw_chars": self.total_raw_chars,
            "compressed_chars": self.total_compressed_chars,
            "char_savings": saving_chars,
            "saving_percent": round(pct, 2),
            "est_raw_tokens": est_raw_tokens,
            "est_comp_tokens": est_comp_tokens,
            "est_token_savings": est_token_savings,
            "ccr_cache_size": len(self.ccr_cache)
        }

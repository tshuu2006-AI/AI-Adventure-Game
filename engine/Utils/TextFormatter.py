import re

class TextFormatter:
    @staticmethod
    def parse_story_into_segments(full_text: str) -> list:
        """Cắt text dựa trên tag [NPC_TALK: Tên] và [PLAYER_TALK] từ LLM"""
        pattern = r'\[(NPC_TALK|PLAYER_TALK)(?::\s*([^\]]*))?\](.*?)\[/\1\]'

        if not re.search(pattern, full_text):
            return TextFormatter.parse_story_fallback(full_text)

        segments = []
        last_end = 0
        for match in re.finditer(pattern, full_text, flags=re.DOTALL):
            narration = full_text[last_end:match.start()].strip()
            if narration:
                for p in narration.split('\n'):
                    if p.strip():
                        segments.append({"speaker": "Master", "text": p.strip()})

            tag_type = match.group(1)
            speaker_name = match.group(2).strip() if match.group(2) else ""
            dialogue = match.group(3).strip()

            if dialogue:
                if tag_type == "NPC_TALK":
                    final_speaker = speaker_name if speaker_name else "NPC"
                    segments.append({"speaker": final_speaker, "text": f'"{dialogue}"'})
                elif tag_type == "PLAYER_TALK":
                    segments.append({"speaker": "Player", "text": f'"{dialogue}"'})

            last_end = match.end()

        remaining_narration = full_text[last_end:].strip()
        if remaining_narration:
            for p in remaining_narration.split('\n'):
                if p.strip():
                    segments.append({"speaker": "Master", "text": p.strip()})

        return segments

    @staticmethod
    def parse_story_fallback(full_text: str) -> list:
        """Fallback an toàn: Cắt text dựa trên ngoặc kép"""
        segments = []
        paragraphs = [p.strip() for p in full_text.split('\n') if p.strip()]
        for p in paragraphs:
            parts = re.split(r'(".*?")', p)
            for part in parts:
                part = part.strip()
                if not part: continue

                if part.startswith('"') and part.endswith('"'):
                    dialogue = part[1:-1].strip()
                    if dialogue:
                        segments.append({"speaker": "NPC", "text": f'"{dialogue}"'})
                else:
                    segments.append({"speaker": "Master", "text": part})
        return segments
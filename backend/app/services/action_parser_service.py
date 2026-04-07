class ActionParserService:
    """Converts natural language into structured change drafts."""

    def parse(self, text: str) -> dict:
        return {"text": text, "status": "draft"}

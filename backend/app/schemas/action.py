from pydantic import BaseModel


class ActionParseRequest(BaseModel):
    text: str


class ActionParseResponse(BaseModel):
    original_text: str
    status: str
    message: str

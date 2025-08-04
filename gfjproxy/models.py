"""Data models.

The name of some fields in here may not match with the source they are from."""

from dataclasses import dataclass, field
from json import loads

################################################################################


@dataclass(kw_only=True)
class JaiMessage:
    """JanitorAI Message."""

    content: str = ""
    role: str = ""

    @staticmethod
    def parse(data: dict | str):
        if isinstance(data, str):
            data = loads(data)
        if not isinstance(data, dict):
            raise TypeError("Invalid data")

        jai_msg = JaiMessage()
        jai_msg.content = data.get("content", "")
        jai_msg.role = data.get("role", "")
        return jai_msg


@dataclass(kw_only=True)
class JaiRequest:
    """JanitorAI Request."""

    max_tokens: int = 0
    messages: list[JaiMessage] = field(default_factory=list)
    model: str = ""
    quiet: bool = False  # This isn't from the request JSON but from the URL
    stream: bool = False
    temperature: int = 0

    @staticmethod
    def parse(data: dict | str):
        if isinstance(data, str):
            data = loads(data)
        if not isinstance(data, dict):
            raise TypeError("Invalid data")

        jai_req = JaiRequest()
        jai_req.max_tokens = data.get("max_tokens", 0)
        jai_req.messages = [
            JaiMessage.parse(jai_msg) for jai_msg in data.get("messages", [])
        ]
        jai_req.model = data.get("model", "")
        jai_req.stream = data.get("stream", False)
        jai_req.temperature = data.get("temperature", 0)
        return jai_req


################################################################################

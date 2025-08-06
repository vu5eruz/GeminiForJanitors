"""Data models.

The name of some fields in here may not match with the source they are from."""

from dataclasses import dataclass, field
from json import loads
from .commands import Command, parse_message, strip_message

################################################################################


@dataclass(kw_only=True)
class JaiMessage:
    """JanitorAI Message."""

    commands: list[Command] = field(default_factory=list)
    content: str = "."
    role: str = "user"

    @staticmethod
    def parse(data: dict | str):
        if isinstance(data, str):
            data = loads(data)
        if not isinstance(data, dict):
            raise TypeError("Invalid data")

        jai_msg = JaiMessage()

        if role := data.get("role"):
            jai_msg.role = role

        if content := data.get("content"):
            if role == "user":
                jai_msg.commands, jai_msg.content = parse_message(content)
            else:
                jai_msg.content = strip_message(content)

        return jai_msg


@dataclass(kw_only=True)
class JaiRequest:
    """JanitorAI Request."""

    max_tokens: int = 0
    messages: list[JaiMessage] = field(default_factory=list)
    model: str = ""
    quiet: bool = False  # This isn't from the request JSON but from the URL
    quiet_commands: bool = False  # This is to make testing easier
    stream: bool = False
    temperature: int = 0
    use_prefill: bool = False  # Set by //prefill command
    use_preset: str = None  # Set by //preset command
    use_nobot: bool = False  # Set by //nobot command

    @staticmethod
    def parse(data: dict | str):
        if isinstance(data, str):
            data = loads(data)
        if not isinstance(data, dict):
            raise TypeError("Invalid data")

        jai_req = JaiRequest()

        if max_tokens := data.get("max_tokens"):
            jai_req.max_tokens = max_tokens

        if messages := data.get("messages"):
            jai_req.messages = [JaiMessage.parse(jai_msg) for jai_msg in messages]

        if model := data.get("model"):
            jai_req.model = model

        if stream := data.get("stream"):
            jai_req.stream = stream

        if temperature := data.get("temperature"):
            jai_req.temperature = temperature

        return jai_req


################################################################################

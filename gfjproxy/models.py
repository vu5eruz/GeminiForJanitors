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
    frequency_penalty: float = 0.0
    repetition_penalty: float = 0.0
    messages: list[JaiMessage] = field(default_factory=list)
    model: str = ""
    quiet: bool = False  # This isn't from the request JSON but from the URL
    quiet_commands: bool = False  # This is to make testing easier
    stream: bool = False
    temperature: int = 0
    top_k: int = 0
    top_p: float = 0.0
    use_advsettings: bool = False  # Set by //advsettings command
    use_prefill: bool = False  # Set by //prefill command
    use_ooctrick: bool = False  # Set by //ooctrick command
    use_preset: str = None  # Set by //preset command
    use_nobot: bool = False  # Set by //nobot command
    use_think: bool = False  # Set by //think command

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

        if model := data.get("model").strip().lower():
            if model.startswith("google/gemini"):  # OpenRouter
                jai_req.model = model.split("/")[1]
            else:
                jai_req.model = model

        if stream := data.get("stream"):
            jai_req.stream = stream

        if temperature := data.get("temperature"):
            jai_req.temperature = temperature

        if top_k := data.get("top_k"):
            jai_req.top_k = top_k

        if top_p := data.get("top_p"):
            jai_req.top_p = top_p

        if frequency_penalty := data.get("frequency_penalty"):
            jai_req.frequency_penalty = frequency_penalty

        if repetition_penalty := data.get("repetition_penalty"):
            jai_req.repetition_penalty = repetition_penalty

        return jai_req


################################################################################

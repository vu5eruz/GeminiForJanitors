"""Data models.

The name of some fields in here may not match with the source they are from."""

from dataclasses import dataclass, field
from json import loads

from google.genai import types

from .commands import Command, parse_message, strip_message

################################################################################


@dataclass(kw_only=True, slots=True)
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


@dataclass(kw_only=True, slots=True)
class JaiRequest:
    """JanitorAI Request."""

    api_key: str = ""
    max_tokens: int = 0
    frequency_penalty: float = 0.0
    repetition_penalty: float = 0.0
    messages: list[JaiMessage] = field(default_factory=list)
    model: str = ""
    quiet: bool = False  # This isn't from the request JSON but from the URL
    quiet_commands: bool = False  # This is to make testing easier
    stream: bool = False
    temperature: float = 0
    top_k: int = 0
    top_p: float = 0.0
    use_advsettings: bool = False  # Set by //advsettings command
    use_dice_char: bool = False  # Set by //dice_char command
    use_nobot: bool = False  # Set by //nobot command
    use_ooctrick: bool = False  # Set by //ooctrick command
    use_prefill: bool = False  # Set by //prefill command
    use_preset: str | None = None  # Set by //preset command
    use_search: bool = False  # Set by //search command
    use_think: bool = False  # Set by //think command
    key_index: int = 1
    key_count: int = 1

    def append_message(self, role: str, content: str):
        self.messages.append(
            JaiMessage(
                content=content,
                role=role,
            )
        )

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
            model = str(model).strip().lower()
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


@dataclass(kw_only=True, slots=True)
class JaiResultMetadata:
    "JanitorAI Generate Content Result Metadata"

    api_key_valid: bool = True
    rejection_feedback: str = ""
    token_usage: types.GenerateContentResponseUsageMetadata | None = None


@dataclass(init=False, kw_only=True, slots=True)
class JaiResult:
    "JanitorAI Generate Content Result"

    status: int
    text: str
    error: str
    extras: str
    metadata: JaiResultMetadata

    def __init__(
        self,
        status: int,
        message: str,
        *,
        extras: str = "",
        metadata: JaiResultMetadata | None = None,
    ):
        self.status = status

        if status == 200:
            self.text = message
            self.error = ""
        else:
            self.text = ""
            self.error = message

        self.extras = extras
        self.metadata = metadata or JaiResultMetadata()

    def __bool__(self) -> bool:
        return self.status == 200


################################################################################

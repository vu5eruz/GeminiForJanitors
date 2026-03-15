"""Data models.

The name of some fields in here may not match with the source they are from."""

from dataclasses import dataclass, field
from json import loads

from google.genai import types

from .commands import Command, parse_message, strip_message
from .utils import comma_split

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

    # Authorization header
    api_key: str = ""
    api_key_index: int = 1
    api_key_count: int = 1

    # Request body
    max_tokens: int = 0
    messages: list[JaiMessage] = field(default_factory=list)
    models: dict[str, str] = field(default_factory=dict)
    stream: bool = False
    temperature: float = 0
    frequency_penalty: float = 0.0
    repetition_penalty: float = 0.0
    top_k: int = 0
    top_p: float = 0.0

    # Request URL
    quiet: bool = False
    quiet_commands: bool = False  # Only for testing

    # Commands
    use_advsettings: bool = False
    use_dice_char: bool = False
    use_nobot: bool = False
    use_ooctrick: bool = False
    use_prefill: bool = False
    use_preset: str | None = None
    use_search: bool = False
    use_think: bool = False

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
            for model in comma_split(model.lower()):
                if "/" in model:
                    provider, model_name = model.split("/", maxsplit=1)
                    jai_req.models[provider] = model_name
                elif model.startswith("gemini-"):
                    jai_req.models["google"] = model
                else:
                    # Build a comma-separated list of unknown models
                    if unknown := jai_req.models.get("unknown"):
                        jai_req.models["unknown"] = f"{unknown}, {model}"
                    else:
                        jai_req.models["unknown"] = model

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

import pytest

from gfjproxy.models import JaiRequest

################################################################################

# From a proxy test
SAMPLE_JAI_REQUEST_1 = {
    "max_tokens": 10,
    "messages": [{"content": "Just say TEST", "role": "user"}],
    "model": "gemini-2.5-pro",
    "temperature": 0,
}


@pytest.mark.parametrize(
    "sample",
    [
        SAMPLE_JAI_REQUEST_1,
    ],
)
def test_jai_request(sample):
    """Basic parsing tests against sample data."""

    jai_req = JaiRequest.parse(sample)

    assert jai_req.max_tokens == sample["max_tokens"]

    assert len(jai_req.messages) == len(sample["messages"])

    for jai_msg, msg in zip(jai_req.messages, sample["messages"]):
        assert jai_msg.content == msg["content"]

        assert jai_msg.role == msg["role"]

    assert jai_req.model == sample["model"]

    # JanitorAI may or may not omit the "stream" key
    if "stream" in sample:
        assert jai_req.stream == sample["stream"]
    else:
        assert not jai_req.stream

    assert jai_req.temperature == sample["temperature"]


################################################################################

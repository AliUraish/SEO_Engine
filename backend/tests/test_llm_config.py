from pydantic import BaseModel

from app.config import Settings
from app.integrations.llm import OpenAILLM


class Result(BaseModel):
    value: str


class FakeResponses:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    async def parse(self, **kwargs):  # type: ignore[no-untyped-def]
        self.kwargs = kwargs
        return type("Response", (), {"output_parsed": Result(value="ok")})()


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_openai_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_REASONING", raising=False)
    settings = Settings(_env_file=None)
    assert settings.openai_base_url == "https://api.openai.com/v1"
    assert settings.openai_reasoning is False


def test_blank_openai_base_url_uses_default():
    settings = Settings(_env_file=None, openai_base_url="")
    assert settings.openai_base_url == "https://api.openai.com/v1"


async def test_reasoning_is_omitted_by_default(monkeypatch):
    monkeypatch.setattr("app.integrations.llm.assert_network", lambda _what: None)
    llm = OpenAILLM("test-model", "test-key")
    client = FakeClient()
    llm.client = client  # type: ignore[assignment]

    result = await llm.structured(system="system", prompt="prompt", schema=Result)

    assert result == Result(value="ok")
    assert "reasoning" not in client.responses.kwargs

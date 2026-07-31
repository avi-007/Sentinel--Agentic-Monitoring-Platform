from common.settings import BaseServiceSettings


class AgentSettings(BaseServiceSettings):
    # "mock" = zero cost, zero API key, deterministic — the default so the
    # whole pipeline is demoable out of the box. Set to "openai" + provide
    # OPENAI_API_KEY for real GPT-4o, or "openrouter" + OPENROUTER_API_KEY
    # for any OpenRouter-hosted model (including free ones).
    llm_provider: str = "mock"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-oss-20b:free"
    agent_max_tool_turns: int = 6
    agent_request_timeout_seconds: float = 30.0
    agent_mock_seed: int = 42
    agent_consumer_group: str = "sentinel-agent"

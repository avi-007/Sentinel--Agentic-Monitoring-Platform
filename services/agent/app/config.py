from common.settings import BaseServiceSettings


class AgentSettings(BaseServiceSettings):
    # "mock" = zero cost, zero API key, deterministic — the default so the
    # whole pipeline is demoable out of the box. Set to "openai" + provide
    # OPENAI_API_KEY to use real GPT-4o.
    llm_provider: str = "mock"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    agent_max_tool_turns: int = 6
    agent_request_timeout_seconds: float = 30.0
    agent_mock_seed: int = 42
    agent_consumer_group: str = "sentinel-agent"

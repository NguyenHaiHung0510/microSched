"""No-egress production dependency/config check, also used by the no-dev CI job."""

from app.core.settings import Settings


def main() -> None:
    # Import the actual frameworks, not just our lazy application wrappers.
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.graph import StateGraph
    from openai import AsyncOpenAI
    from psycopg import AsyncConnection

    assert all(
        callable(item) for item in (AsyncPostgresSaver, StateGraph, AsyncOpenAI, AsyncConnection)
    )
    config = Settings(
        _env_file=None,
        app_env="production",
        oauth_state_secret="runtime-check-synthetic",
        mimi_public_origin="https://alpha.example.invalid",
        mimi_real_chat_enabled=True,
        mimi_live_provider_enabled=True,
        mimi_context_v1_enabled=True,
        mimi_runner="langgraph",
        mimi_transport="openai_sdk",
        mimi_text_response_format="natural",
        mimi_standard_api_key="synthetic-never-dispatched",
        mimi_route_model="deepseek/deepseek-v4.1-flash",
        mimi_route_provider="deepinfra",
        mimi_route_quantization="fp8",
        mimi_route_reasoning_effort="high",
        mimi_route_max_input_price=0.2,
        mimi_route_max_output_price=0.6,
    )
    assert config.is_production and config.mimi_compaction_trigger_tokens == 100_000
    print("Mimi alpha production config and no-dev framework imports PASS; no egress")


if __name__ == "__main__":
    main()

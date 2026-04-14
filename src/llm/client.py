"""
Multi-backend LLM client factory.
Creates AutoGen-compatible ChatCompletionClient instances for any supported backend.
"""

from __future__ import annotations

from loguru import logger
from config.settings import settings


def create_llm_client(
    backend: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
):
    """
    Factory that returns an AutoGen ChatCompletionClient.

    Falls back to settings values for any parameter not explicitly provided.
    """
    backend = backend or settings.llm_backend
    model = model or settings.llm_model
    api_key = api_key or settings.llm_api_key
    base_url = base_url or settings.llm_base_url

    if backend == "ollama":
        return _create_ollama(model, base_url)
    elif backend == "openai":
        return _create_openai(model, api_key, base_url)
    elif backend == "claude":
        return _create_claude(model, api_key)
    elif backend == "deepseek":
        return _create_deepseek(model, api_key)
    elif backend == "gemini":
        return _create_gemini(model, api_key)
    else:
        raise ValueError(f"Unknown LLM backend: {backend}")


def _create_ollama(model: str, base_url: str | None):
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    url = base_url or settings.ollama_base_url
    logger.info(f"Creating Ollama client: model={model}, url={url}")
    return OpenAIChatCompletionClient(
        model=model,
        api_key="ollama",
        base_url=f"{url.rstrip('/')}/v1",
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "family": "unknown",
        },
    )


def _create_openai(model: str, api_key: str, base_url: str | None):
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    kwargs: dict = {"model": model, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    logger.info(f"Creating OpenAI client: model={model}")
    return OpenAIChatCompletionClient(**kwargs)


def _create_claude(model: str, api_key: str):
    try:
        from autogen_ext.models.anthropic import AnthropicChatCompletionClient
        logger.info(f"Creating Claude client (native): model={model}")
        return AnthropicChatCompletionClient(model=model, api_key=api_key)
    except ImportError:
        from autogen_ext.models.openai import OpenAIChatCompletionClient
        logger.info(f"Creating Claude client (via LiteLLM proxy): model={model}")
        return OpenAIChatCompletionClient(
            model=model,
            api_key=api_key,
            base_url="http://localhost:4000/v1",
            model_info={
                "vision": False,
                "function_calling": True,
                "json_output": True,
                "family": "unknown",
            },
        )


def _create_deepseek(model: str, api_key: str):
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    model = model if model != settings.llm_model else "deepseek-chat"
    logger.info(f"Creating DeepSeek client: model={model}")
    return OpenAIChatCompletionClient(
        model=model,
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "family": "unknown",
        },
    )


def _create_gemini(model: str, api_key: str):
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    if model in ("", settings.llm_model) or "gemma" in model or "llama" in model:
        model = "gemini-3.1-flash-lite-preview"
    logger.info(f"Creating Gemini client: model={model}")
    return OpenAIChatCompletionClient(
        model=model,
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "family": "unknown",
        },
    )

"""Multi-provider LLM client with automatic fallback (Groq → Gemini → OpenAI).

Uses LangChain chat model abstractions so every downstream agent, workflow,
and service gets a uniform interface regardless of the active provider.
"""

import logging
import os
from functools import lru_cache
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from backend.app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMProvider:
    """Manage LLM provider selection, initialization and fallback."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._chat_model: BaseChatModel | None = None
        self._provider_name: str = "none"
        self._configure_langsmith()

    # ------------------------------------------------------------------
    # LangSmith tracing
    # ------------------------------------------------------------------
    def _configure_langsmith(self) -> None:
        """Set LangSmith environment variables for automatic tracing."""
        if self._settings.langchain_tracing_v2 and self._settings.langsmith_api_key:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_PROJECT"] = self._settings.langchain_project
            os.environ["LANGSMITH_API_KEY"] = self._settings.langsmith_api_key.get_secret_value()
            logger.info("LangSmith tracing enabled for project=%s", self._settings.langchain_project)

    # ------------------------------------------------------------------
    # Provider initialization
    # ------------------------------------------------------------------
    def _init_groq(self) -> BaseChatModel | None:
        """Initialize Groq LLM with available model resolution."""
        if not self._settings.groq_api_key:
            return None
        try:
            from langchain_groq import ChatGroq
            from groq import Groq

            groq_key = self._settings.groq_api_key.get_secret_value()
            target_model = self._settings.default_llm
            try:
                g_client = Groq(api_key=groq_key)
                available = [m.id for m in g_client.models.list().data]
                if target_model not in available:
                    preferred = ["llama-3.3-70b-versatile", "qwen/qwen3.8-27b", "openai/gpt-oss-120b"]
                    target_model = next((m for m in preferred if m in available), available[0] if available else target_model)
            except Exception:
                pass

            model = ChatGroq(
                api_key=groq_key,
                model=target_model,
                temperature=0.1,
                max_tokens=4096,
                timeout=30.0,
            )
            self._provider_name = "groq"
            logger.info("Groq LLM initialized model=%s", target_model)
            return model
        except Exception:
            logger.warning("Groq initialization failed, trying fallback", exc_info=True)
            return None

    def _init_gemini(self) -> BaseChatModel | None:
        """Initialize Google Gemini LLM."""
        if not self._settings.gemini_api_key:
            return None
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            model = ChatGoogleGenerativeAI(
                api_key=self._settings.gemini_api_key.get_secret_value(),
                model="gemini-2.5-flash",
                temperature=0.1,
                max_output_tokens=4096,
                timeout=30.0,
            )
            self._provider_name = "gemini"
            logger.info("Gemini LLM initialized")
            return model
        except Exception:
            logger.warning("Gemini initialization failed, trying fallback", exc_info=True)
            return None

    def _init_openai(self) -> BaseChatModel | None:
        """Initialize OpenAI LLM."""
        if not self._settings.openai_api_key:
            return None
        try:
            from langchain_openai import ChatOpenAI

            model = ChatOpenAI(
                api_key=self._settings.openai_api_key.get_secret_value(),
                model="gpt-4o-mini",
                temperature=0.1,
                max_tokens=4096,
                timeout=30.0,
            )
            self._provider_name = "openai"
            logger.info("OpenAI LLM initialized")
            return model
        except Exception:
            logger.warning("OpenAI initialization failed", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    @property
    def chat_model(self) -> BaseChatModel:
        """Return the active chat model with automatic fallback chain."""
        if self._chat_model is None:
            for initializer in (self._init_groq, self._init_gemini, self._init_openai):
                model = initializer()
                if model is not None:
                    self._chat_model = model
                    break
            if self._chat_model is None:
                raise RuntimeError("No LLM provider available. Check API keys in .env")
        return self._chat_model

    @property
    def provider_name(self) -> str:
        """Return the name of the currently active provider."""
        _ = self.chat_model  # Ensure initialization
        return self._provider_name

    async def chat(
        self,
        message: str,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """Send a chat message and return the response text with runtime provider fallback."""
        if not message or not str(message).strip():
            raise ValueError("Message content cannot be empty.")

        messages: list[BaseMessage] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        if history:
            for msg in history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))
        messages.append(HumanMessage(content=message))

        initializers = [
            ("groq", self._init_groq),
            ("gemini", self._init_gemini),
            ("openai", self._init_openai),
        ]
        last_error = None
        for prov_name, init_fn in initializers:
            try:
                candidate = init_fn()
                if candidate is None:
                    continue
                response = await candidate.ainvoke(messages)
                self._chat_model = candidate
                self._provider_name = prov_name
                return str(response.content)
            except (ValueError, TypeError) as val_err:
                # Do not retry invalid user inputs across providers
                raise val_err
            except Exception as e:
                last_error = e
                logger.warning("Provider %s call failed, trying next provider in chain: %s", prov_name, e)
                continue

        if last_error:
            raise last_error
        raise RuntimeError("No LLM provider available.")

    async def chat_with_json(
        self,
        message: str,
        system_prompt: str | None = None,
    ) -> str:
        """Send a chat message requesting JSON output."""
        json_instruction = (
            "You must respond with valid JSON only. No markdown, no explanations, "
            "no code fences. Just the raw JSON object."
        )
        full_system = f"{system_prompt}\n\n{json_instruction}" if system_prompt else json_instruction
        return await self.chat(message, system_prompt=full_system)

    async def stream(
        self,
        message: str,
        system_prompt: str | None = None,
    ) -> Any:
        """Stream a chat response token by token."""
        messages: list[BaseMessage] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=message))

        async for chunk in self.chat_model.astream(messages):
            yield str(chunk.content)


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Return a singleton LLM provider instance."""
    return LLMProvider(get_settings())

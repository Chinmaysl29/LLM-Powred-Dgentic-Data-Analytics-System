"""Request-local provider ordering for intent classification; no shared mutation."""
import asyncio
from copy import copy
from threading import BoundedSemaphore
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from backend.app.llm.provider import LLMProvider
from backend.app.learning.evidence import enabled
from backend.app.learning.selection_models import PROVIDERS
from backend.app.learning.selection_runtime import decision

_preflight_slots = BoundedSemaphore(2)


class ScopedProvider:
    def __init__(self, base, actor, dataset_id, dataset_version):
        self.base, self.actor, self.dataset_id, self.dataset_version = base, actor, dataset_id, dataset_version

    def prepare(self, pinned, available):
        if not _preflight_slots.acquire(blocking=False):
            return None
        try:
            local = copy(self.base)
            local._chat_model = None; local._provider_name = 'none'
            ready = {}
            for name in available:
                model = getattr(local, '_init_' + name)()
                identity = getattr(model, 'model', None) if name == 'gemini' else getattr(model, 'model_name', None)
                if model is None or identity != pinned[name]:
                    return None
                ready[name] = model
            return ready
        except Exception:
            return None
        finally:
            _preflight_slots.release()

    async def chat(self, message, system_prompt=None, history=None):
        if not message or not str(message).strip():
            raise ValueError('Message content cannot be empty.')
        available = [p for p in PROVIDERS if getattr(self.base._settings, p + '_api_key', None)]
        selected = await decision(self.actor, self.dataset_id, self.dataset_version, 'provider', available)
        if not selected or selected['choice'] not in available:
            return await self.base.chat(message, system_prompt=system_prompt, history=history)
        try:
            ready = await asyncio.wait_for(asyncio.to_thread(self.prepare, selected['model']['models'], available), timeout=5)
        except Exception:
            ready = None
        if not ready:
            return await self.base.chat(message, system_prompt=system_prompt, history=history)
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        for item in history or []:
            if item['role'] == 'user':
                messages.append(HumanMessage(content=item['content']))
            elif item['role'] == 'assistant':
                messages.append(AIMessage(content=item['content']))
        messages.append(HumanMessage(content=message))
        order = [selected['choice'], *(p for p in available if p != selected['choice'])]
        error = None
        for name in order:
            try:
                response = await ready[name].ainvoke(messages)
                return str(response.content)
            except (ValueError, TypeError):
                raise  # Preserve the existing invalid-input retry policy.
            except Exception as exc:
                error = exc
        if error:
            raise error
        raise RuntimeError('No LLM provider available.')

    async def chat_with_json(self, message, system_prompt=None):
        # Reuse the exact existing JSON instruction without changing any prompt.
        return await LLMProvider.chat_with_json(self, message, system_prompt)


def scoped_classifier(service, actor, dataset_id, dataset_version=None):
    if not enabled() or not actor or not dataset_id:
        return service
    from backend.app.services.intent_classification_service import IntentClassificationService
    if type(service) is not IntentClassificationService or type(service._llm) is not LLMProvider:
        return service
    available = [p for p in PROVIDERS if getattr(service._llm._settings, p + '_api_key', None)]
    if len(available) < 2:
        return service
    return IntentClassificationService(llm=ScopedProvider(service._llm, actor, dataset_id, dataset_version), registry=service.registry)

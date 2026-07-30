"""A provider that returns whatever you hand it, in order.

For tests and for offline development. It records every request it receives, so
tests can assert on the prompt that was actually built — which is how the
untrusted-input delimiting is verified without a live model.

This is a stand-in for a *provider*, not for a diagram render: nothing here
stubs out work that the product's correctness depends on.
"""

from llm.errors import ProviderError
from llm.providers.base import ProviderRequest, ProviderResponse

ScriptedItem = str | tuple[str, int, int] | BaseException


class ScriptedProvider:
    def __init__(self, responses: list[ScriptedItem], name: str = "scripted") -> None:
        self.name = name
        self._responses: list[ScriptedItem] = list(responses)
        self.requests: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)

        if not self._responses:
            raise ProviderError("scripted provider exhausted: more calls than scripted responses")

        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item

        if isinstance(item, tuple):
            text, input_tokens, output_tokens = item
        else:
            text, input_tokens, output_tokens = item, 0, 0

        return ProviderResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=request.model,
        )

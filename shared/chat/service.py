"""Chat edit-intent parsing: one message, plus the model it is about, in — one
parsed intent out. Never a mutation. (C-3)

The current CPM is serialised into the same string as the chat message and
handed to the gateway as a single block of data (FR-3/NFR-S3) — exactly how
`ExtractionService` hands the gateway a description. Neither the message nor
the model state is ever anywhere but inside that block.
"""

from cpm.schema import CPMDraft
from llm.gateway import LLMGateway
from review import EditIn

from .intent import ChatEditIntent
from .result import ChatParseResult, Clarify, NotAnEdit, ParsedEdit


class ChatEditService:
    def __init__(self, gateway: LLMGateway, task_name: str = "chat_edit_intent") -> None:
        self._gateway = gateway
        self._task_name = task_name

    async def parse(
        self, message: str, draft: CPMDraft, *, user_id: str | None = None
    ) -> ChatParseResult:
        combined = (
            f"Current model:\n{draft.model_dump_json(by_alias=True)}\n\nChat message:\n{message}"
        )
        raw = await self._gateway.complete(
            self._task_name, combined, ChatEditIntent, user_id=user_id
        )

        # Precedence when the model does not cleanly pick one shape: a
        # clarifying question always wins, because asking is never wrong.
        # Below that, no op at all falls back to "not an edit" rather than
        # inventing one — never guess.
        if raw.clarify:
            return Clarify(question=raw.clarify)
        if raw.notAnEdit or raw.op is None:
            return NotAnEdit()

        # Never trusted directly: the same strict model a form submission
        # builds, so a parsed op fails exactly as a malformed request would.
        edit = EditIn.model_validate(
            {
                "op": raw.op,
                "id": raw.id,
                "name": raw.name,
                "entityId": raw.entityId,
                "fromId": raw.fromId,
                "toId": raw.toId,
                "type": raw.type,
                "label": raw.label,
                "cardinality": raw.cardinality,
                "attributeName": raw.attributeName,
                "attributeType": raw.attributeType,
                "actorIds": raw.actorIds,
            }
        )
        return ParsedEdit(edit=edit)

"""A2A Protocol API routes — conversations, messages, agent registry."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from domain.entities.a2a import AgentDescriptor
from domain.value_objects.a2a import A2AAction
from domain.value_objects.agent_engine import AgentEngineType
from interface.api.schemas import (
    AgentDescriptorResponse,
    AgentListResponse,
    CollectRepliesResponse,
    ConversationCheckResponse,
    ConversationResponse,
    CreateConversationRequest,
    RegisterAgentRequest,
    ReplyMessageRequest,
    SendMessageRequest,
    SendResultResponse,
)

router = APIRouter(prefix="/api/a2a", tags=["a2a"])


def _container(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.container


def _parse_engine(value: str) -> AgentEngineType:
    try:
        return AgentEngineType(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown engine type: {value}") from exc


def _parse_action(value: str) -> A2AAction:
    try:
        return A2AAction(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown action: {value}") from exc


# ---------- Conversations ----------


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    body: CreateConversationRequest, request: Request
) -> ConversationResponse:
    """Create a new A2A conversation."""
    c = _container(request)
    participants = [_parse_engine(p) for p in body.participants]
    conv = c.manage_a2a_conversation.create(
        task_id=body.task_id,
        participants=participants,
        ttl_seconds=body.ttl_seconds,
    )
    c.a2a_conversations[conv.id] = conv
    summary = c.manage_a2a_conversation.summarize(conv)
    return ConversationResponse.from_conversation(conv, summary)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str, request: Request) -> ConversationResponse:
    """Get conversation state and messages."""
    c = _container(request)
    conv = c.a2a_conversations.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    summary = c.manage_a2a_conversation.summarize(conv)
    return ConversationResponse.from_conversation(conv, summary)


@router.post(
    "/conversations/{conversation_id}/check",
    response_model=ConversationCheckResponse,
)
async def check_conversation(conversation_id: str, request: Request) -> ConversationCheckResponse:
    """Check if conversation is expired or complete."""
    c = _container(request)
    conv = c.a2a_conversations.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    expired = c.manage_a2a_conversation.check_expired(conv)
    complete = c.manage_a2a_conversation.check_complete(conv)
    return ConversationCheckResponse(
        expired=expired,
        complete=complete,
        status=conv.status.value,
    )


@router.post(
    "/conversations/{conversation_id}/collect",
    response_model=CollectRepliesResponse,
)
async def collect_replies(conversation_id: str, request: Request) -> CollectRepliesResponse:
    """Collect pending replies from the broker."""
    c = _container(request)
    conv = c.a2a_conversations.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    new_count = await c.manage_a2a_conversation.collect_replies(conv, timeout=2.0)
    return CollectRepliesResponse(
        new_replies=new_count,
        total_messages=conv.message_count,
    )


# ---------- Messages ----------


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=SendResultResponse,
    status_code=201,
)
async def send_message(
    conversation_id: str, body: SendMessageRequest, request: Request
) -> SendResultResponse:
    """Send a message in a conversation."""
    c = _container(request)
    conv = c.a2a_conversations.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    sender = _parse_engine(body.sender)
    action = _parse_action(body.action)
    receiver = _parse_engine(body.receiver) if body.receiver else None
    result = await c.send_a2a_message.execute(
        sender=sender,
        action=action,
        conversation=conv,
        payload=body.payload,
        receiver=receiver,
        artifacts=body.artifacts or None,
    )
    return SendResultResponse.from_result(result)


@router.post(
    "/conversations/{conversation_id}/reply",
    response_model=SendResultResponse,
    status_code=201,
)
async def reply_message(
    conversation_id: str, body: ReplyMessageRequest, request: Request
) -> SendResultResponse:
    """Reply to a specific message in a conversation."""
    c = _container(request)
    conv = c.a2a_conversations.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    # Find the request message to reply to
    request_msg = next((m for m in conv.messages if m.id == body.message_id), None)
    if request_msg is None:
        raise HTTPException(
            status_code=404,
            detail=f"Message {body.message_id} not found in conversation",
        )
    sender = _parse_engine(body.sender)
    result = await c.send_a2a_message.reply(
        sender=sender,
        request=request_msg,
        conversation=conv,
        payload=body.payload,
        artifacts=body.artifacts or None,
    )
    return SendResultResponse.from_result(result)


# ---------- Agent Registry ----------


@router.get("/agents", response_model=AgentListResponse)
async def list_agents(request: Request) -> AgentListResponse:
    """List registered agents."""
    c = _container(request)
    agents = await c.agent_registry.list_available()
    return AgentListResponse(
        agents=[
            AgentDescriptorResponse(
                agent_id=a.agent_id,
                engine_type=a.engine_type.value,
                capabilities=list(a.capabilities),
                status=a.status,
                last_seen=a.last_seen,
            )
            for a in agents
        ],
        count=len(agents),
    )


@router.post("/agents", response_model=AgentDescriptorResponse, status_code=201)
async def register_agent(body: RegisterAgentRequest, request: Request) -> AgentDescriptorResponse:
    """Register an agent in the registry."""
    c = _container(request)
    engine = _parse_engine(body.engine_type)
    descriptor = AgentDescriptor(
        engine_type=engine,
        capabilities=body.capabilities,
    )
    await c.agent_registry.register(descriptor)
    return AgentDescriptorResponse(
        agent_id=descriptor.agent_id,
        engine_type=descriptor.engine_type.value,
        capabilities=list(descriptor.capabilities),
        status=descriptor.status,
        last_seen=descriptor.last_seen,
    )


@router.delete("/agents/{agent_id}", status_code=204)
async def deregister_agent(agent_id: str, request: Request) -> None:
    """Remove an agent from the registry."""
    c = _container(request)
    await c.agent_registry.deregister(agent_id)

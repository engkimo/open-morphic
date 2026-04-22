"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, XCircle, Network } from "lucide-react";
import {
  listAgents,
  registerAgent,
  deregisterAgent,
  createConversation,
  getConversation,
  sendA2AMessage,
  type AgentDescriptorResponse,
  type ConversationResponse,
  type A2AMessageResponse,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

const ENGINE_OPTIONS = [
  "ollama",
  "claude_code",
  "gemini_cli",
  "codex_cli",
  "openhands",
  "direct_llm",
];

const ACTION_OPTIONS = [
  "solve",
  "review",
  "delegate",
  "report",
  "request_info",
  "handoff",
];

// ── Agent Registry ──

function AgentCard({
  agent,
  onDeregister,
}: {
  agent: AgentDescriptorResponse;
  onDeregister: (id: string) => void;
}) {
  const isOnline = agent.status === "available" || agent.status === "online";

  return (
    <Card className="transition-colors hover:border-accent">
      <CardContent className="p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            {isOnline ? (
              <CheckCircle2 size={14} className="text-success" />
            ) : (
              <XCircle size={14} className="text-danger" />
            )}
            <span className="font-mono text-sm font-semibold">
              {agent.engine_type}
            </span>
          </div>
          <Button
            variant="ghost"
            size="xs"
            onClick={() => onDeregister(agent.agent_id)}
            className="text-text-muted hover:text-destructive"
          >
            Remove
          </Button>
        </div>
        <div className="text-xs text-text-muted mb-2">
          ID: {agent.agent_id.slice(0, 12)}...
        </div>
        <div className="flex flex-wrap gap-1.5">
          {agent.capabilities.map((cap) => (
            <Badge key={cap} variant="engine" className="text-[10px]">
              {cap}
            </Badge>
          ))}
          {agent.capabilities.length === 0 && (
            <span className="text-[10px] text-text-muted">No capabilities</span>
          )}
        </div>
        <div className="mt-2 text-[10px] text-text-muted">
          Last seen: {new Date(agent.last_seen).toLocaleString()}
        </div>
      </CardContent>
    </Card>
  );
}

function AgentRegistry() {
  const [agents, setAgents] = useState<AgentDescriptorResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [showRegister, setShowRegister] = useState(false);
  const [newEngine, setNewEngine] = useState("ollama");
  const [newCaps, setNewCaps] = useState("");
  const [registering, setRegistering] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listAgents();
      setAgents(data.agents);
    } catch {
      /* backend may be down */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    setRegistering(true);
    try {
      const caps = newCaps
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);
      await registerAgent(newEngine, caps);
      setShowRegister(false);
      setNewCaps("");
      await refresh();
    } catch {
      /* ignore */
    } finally {
      setRegistering(false);
    }
  }

  async function handleDeregister(agentId: string) {
    try {
      await deregisterAgent(agentId);
      await refresh();
    } catch {
      /* ignore */
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-text-muted">
            Agent Registry ({agents.length})
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button size="xs" onClick={() => setShowRegister(!showRegister)}>
              {showRegister ? "Cancel" : "+ Register"}
            </Button>
            <Button
              variant="secondary"
              size="xs"
              onClick={refresh}
              disabled={loading}
            >
              Refresh
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {showRegister && (
          <form
            onSubmit={handleRegister}
            className="flex items-end gap-3 rounded border border-border bg-background p-3"
          >
            <div className="flex-shrink-0">
              <label className="block text-[10px] text-text-muted mb-1">
                Engine
              </label>
              <select
                value={newEngine}
                onChange={(e) => setNewEngine(e.target.value)}
                className="rounded-md border border-input bg-transparent px-2 py-1.5 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {ENGINE_OPTIONS.map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex-1">
              <label className="block text-[10px] text-text-muted mb-1">
                Capabilities (comma-separated)
              </label>
              <Input
                type="text"
                value={newCaps}
                onChange={(e) => setNewCaps(e.target.value)}
                placeholder="code, review, test"
                className="h-7 text-xs"
              />
            </div>
            <Button
              type="submit"
              size="xs"
              disabled={registering}
              className="bg-success hover:bg-success/80"
            >
              {registering ? "..." : "Register"}
            </Button>
          </form>
        )}

        {loading ? (
          <p className="py-4 text-center text-sm text-text-muted">Loading...</p>
        ) : agents.length === 0 ? (
          <p className="py-4 text-center text-sm text-text-muted">
            No agents registered.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {agents.map((agent) => (
              <AgentCard
                key={agent.agent_id}
                agent={agent}
                onDeregister={handleDeregister}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Conversations ──

function MessageBubble({ msg }: { msg: A2AMessageResponse }) {
  const isResponse = msg.message_type === "response";
  const hasArtifacts = Object.keys(msg.artifacts).length > 0;

  return (
    <div
      className={cn(
        "rounded-lg border p-3",
        isResponse
          ? "border-success/30 bg-success/5 ml-8"
          : "border-accent/30 bg-accent/5 mr-8",
      )}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-semibold text-accent">
            {msg.sender}
          </span>
          {msg.receiver && (
            <>
              <span className="text-[10px] text-text-muted">&rarr;</span>
              <span className="font-mono text-xs text-text-muted">
                {msg.receiver}
              </span>
            </>
          )}
          <Badge
            variant={isResponse ? "success" : "info"}
            className="text-[9px] px-1.5 py-0"
          >
            {msg.action}
          </Badge>
        </div>
        <span className="text-[10px] text-text-muted">
          {new Date(msg.timestamp).toLocaleTimeString()}
        </span>
      </div>
      <p className="text-xs text-foreground whitespace-pre-wrap">
        {msg.payload}
      </p>
      {hasArtifacts && (
        <div className="mt-2 space-y-1">
          {Object.entries(msg.artifacts).map(([key, value]) => (
            <div
              key={key}
              className="rounded border border-border bg-background p-2"
            >
              <span className="font-mono text-[10px] text-text-muted">
                {key}:
              </span>
              <pre className="whitespace-pre-wrap font-mono text-[10px] text-foreground mt-0.5">
                {value.length > 200 ? value.slice(0, 200) + "..." : value}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ConversationDetail({
  conv,
  onClose,
}: {
  conv: ConversationResponse;
  onClose: () => void;
}) {
  const [msgSender, setMsgSender] = useState("claude_code");
  const [msgAction, setMsgAction] = useState("solve");
  const [msgPayload, setMsgPayload] = useState("");
  const [msgReceiver, setMsgReceiver] = useState("");
  const [sending, setSending] = useState(false);
  const [current, setCurrent] = useState(conv);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!msgPayload.trim()) return;
    setSending(true);
    try {
      await sendA2AMessage(
        current.id,
        msgSender,
        msgAction,
        msgPayload.trim(),
        msgReceiver || undefined,
      );
      // Refresh conversation
      const updated = await getConversation(current.id);
      setCurrent(updated);
      setMsgPayload("");
    } catch {
      /* ignore */
    } finally {
      setSending(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>
              Conversation: {current.id.slice(0, 12)}...
            </CardTitle>
            <div className="flex items-center gap-3 mt-1 text-xs text-text-muted">
              <span>Task: {current.task_id}</span>
              <Badge
                variant={
                  current.status === "active"
                    ? "info"
                    : current.status === "resolved"
                      ? "success"
                      : "secondary"
                }
                className="text-[10px]"
              >
                {current.status}
              </Badge>
              <span>
                {current.message_count} msgs / {current.pending_count} pending
              </span>
            </div>
          </div>
          <Button variant="ghost" size="xs" onClick={onClose}>
            Close
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Participants */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-text-muted">Participants:</span>
          {current.participants.map((p) => (
            <Badge key={p} variant="engine" className="text-[10px]">
              {p}
            </Badge>
          ))}
        </div>

        {/* Messages */}
        <ScrollArea className="max-h-96">
          <div className="space-y-3">
            {current.messages.length === 0 ? (
              <p className="py-4 text-center text-xs text-text-muted">
                No messages yet.
              </p>
            ) : (
              current.messages.map((msg) => (
                <MessageBubble key={msg.id} msg={msg} />
              ))
            )}
          </div>
        </ScrollArea>

        {/* Send message form */}
        {current.status === "active" && (
          <form
            onSubmit={handleSend}
            className="rounded border border-border bg-background p-3 space-y-2"
          >
            <div className="flex gap-2">
              <select
                value={msgSender}
                onChange={(e) => setMsgSender(e.target.value)}
                className="rounded-md border border-input bg-transparent px-2 py-1 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {ENGINE_OPTIONS.map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </select>
              <select
                value={msgAction}
                onChange={(e) => setMsgAction(e.target.value)}
                className="rounded-md border border-input bg-transparent px-2 py-1 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {ACTION_OPTIONS.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
              <select
                value={msgReceiver}
                onChange={(e) => setMsgReceiver(e.target.value)}
                className="rounded-md border border-input bg-transparent px-2 py-1 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="">Broadcast</option>
                {ENGINE_OPTIONS.map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex gap-2">
              <Input
                type="text"
                value={msgPayload}
                onChange={(e) => setMsgPayload(e.target.value)}
                placeholder="Message payload..."
                disabled={sending}
                className="flex-1 h-7 text-xs"
              />
              <Button
                type="submit"
                size="xs"
                disabled={sending || !msgPayload.trim()}
              >
                {sending ? "..." : "Send"}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

function ConversationList() {
  const [conversations, setConversations] = useState<ConversationResponse[]>(
    [],
  );
  const [selected, setSelected] = useState<ConversationResponse | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newTaskId, setNewTaskId] = useState("");
  const [newParticipants, setNewParticipants] = useState<string[]>([
    "claude_code",
    "gemini_cli",
  ]);
  const [creating, setCreating] = useState(false);

  function toggleParticipant(engine: string) {
    setNewParticipants((prev) =>
      prev.includes(engine)
        ? prev.filter((p) => p !== engine)
        : [...prev, engine],
    );
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newTaskId.trim() || newParticipants.length < 1) return;
    setCreating(true);
    try {
      const conv = await createConversation(newTaskId.trim(), newParticipants);
      setConversations((prev) => [conv, ...prev]);
      setShowCreate(false);
      setNewTaskId("");
      setSelected(conv);
    } catch {
      /* ignore */
    } finally {
      setCreating(false);
    }
  }

  const statusColor = (status: string) => {
    if (status === "active") return "text-info";
    if (status === "resolved") return "text-success";
    if (status === "expired") return "text-warning";
    return "text-text-muted";
  };

  return (
    <div className="space-y-4">
      {/* Create button */}
      <div className="flex items-center justify-between">
        <h3 className="font-mono text-sm font-semibold text-text-muted">
          Conversations ({conversations.length})
        </h3>
        <Button size="xs" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? "Cancel" : "+ New Conversation"}
        </Button>
      </div>

      {/* Create form */}
      {showCreate && (
        <Card>
          <CardContent className="p-3 space-y-3">
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label className="block text-[10px] text-text-muted mb-1">
                  Task ID
                </label>
                <Input
                  type="text"
                  value={newTaskId}
                  onChange={(e) => setNewTaskId(e.target.value)}
                  placeholder="task-001"
                  className="h-7 text-xs"
                />
              </div>
              <div>
                <label className="block text-[10px] text-text-muted mb-1">
                  Participants
                </label>
                <div className="flex flex-wrap gap-2">
                  {ENGINE_OPTIONS.map((engine) => (
                    <Button
                      key={engine}
                      type="button"
                      variant={newParticipants.includes(engine) ? "default" : "outline"}
                      size="xs"
                      onClick={() => toggleParticipant(engine)}
                      className="font-mono text-[10px]"
                    >
                      {engine}
                    </Button>
                  ))}
                </div>
              </div>
              <Button
                type="submit"
                size="xs"
                disabled={creating || !newTaskId.trim() || newParticipants.length < 1}
                className="bg-success hover:bg-success/80"
              >
                {creating ? "Creating..." : "Create Conversation"}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Selected conversation detail */}
      {selected && (
        <ConversationDetail
          conv={selected}
          onClose={() => setSelected(null)}
        />
      )}

      {/* Conversation list */}
      {conversations.length === 0 && !showCreate ? (
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-sm text-text-muted">
              No conversations yet. Create one to start agent-to-agent
              communication.
            </p>
          </CardContent>
        </Card>
      ) : (
        !selected && (
          <div className="space-y-2">
            {conversations.map((conv) => (
              <Card
                key={conv.id}
                className="cursor-pointer transition-colors hover:border-accent"
                onClick={() => setSelected(conv)}
              >
                <CardContent className="p-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-xs font-semibold">
                        {conv.task_id}
                      </span>
                      <span
                        className={cn("text-[10px] font-medium", statusColor(conv.status))}
                      >
                        {conv.status}
                      </span>
                    </div>
                    <span className="text-[10px] text-text-muted">
                      {conv.message_count} msgs
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 mt-1">
                    {conv.participants.map((p) => (
                      <Badge key={p} variant="engine" className="text-[9px] px-1.5 py-0">
                        {p}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )
      )}
    </div>
  );
}

// ── Main Page ──

export default function A2APage() {
  const [tab, setTab] = useState<string>("conversations");

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="link" size="sm" asChild>
          <Link href="/">&larr; Dashboard</Link>
        </Button>
        <h1 className="font-mono text-lg font-semibold tracking-tight flex items-center gap-2">
          <Network size={18} className="text-accent" />
          A2A Protocol
        </h1>
      </div>

      {/* Info banner */}
      <Card className="border-accent/30 bg-accent/5">
        <CardContent className="p-3 text-sm">
          <p className="text-text-muted">
            <span className="font-semibold text-accent">
              Agent-to-Agent Communication
            </span>
            {" "}&mdash; Google A2A Protocol compliant. Create conversations between
            engine agents, send messages with actions (solve, review, delegate,
            handoff), and manage the agent registry.
          </p>
        </CardContent>
      </Card>

      {/* Tab switching */}
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="conversations">Conversations</TabsTrigger>
          <TabsTrigger value="agents">Agent Registry</TabsTrigger>
        </TabsList>
        <TabsContent value="conversations">
          <ConversationList />
        </TabsContent>
        <TabsContent value="agents">
          <AgentRegistry />
        </TabsContent>
      </Tabs>
    </div>
  );
}

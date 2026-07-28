import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitFork, MessageSquarePlus, Pencil, Send, Trash2 } from "lucide-react";
import { api } from "../api/client";
import { Button, Input } from "../components/ui";
import { cn } from "../lib/utils";

type ChatMessage = {
  id?: number;
  role: string;
  content: string;
  pending?: boolean;
};

type ContextMenuState = {
  conversationId: number;
  x: number;
  y: number;
};

export default function AdvisorPage() {
  const qc = useQueryClient();
  const [activeId, setActiveId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [localMessages, setLocalMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [sending, setSending] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const contextMenuRef = useRef<HTMLDivElement>(null);

  const conversations = useQuery({
    queryKey: ["advisorConversations"],
    queryFn: api.advisorConversations,
  });

  const messagesQuery = useQuery({
    queryKey: ["advisorMessages", activeId],
    queryFn: () => api.advisorConversationMessages(activeId!),
    enabled: activeId != null,
  });

  useEffect(() => {
    if (activeId != null) return;
    const first = conversations.data?.[0];
    if (first) setActiveId(first.id);
  }, [conversations.data, activeId]);

  useEffect(() => {
    if (sending) return;
    if (!messagesQuery.data) {
      if (activeId == null) setLocalMessages([]);
      return;
    }
    setLocalMessages(
      messagesQuery.data.map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
      }))
    );
  }, [messagesQuery.data, activeId, sending]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [localMessages, activeId]);

  useEffect(() => {
    if (renamingId == null) return;
    renameInputRef.current?.focus();
    renameInputRef.current?.select();
  }, [renamingId]);

  useEffect(() => {
    if (!contextMenu) return;
    const close = (e: MouseEvent) => {
      if (contextMenuRef.current?.contains(e.target as Node)) return;
      setContextMenu(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setContextMenu(null);
    };
    const onScroll = () => setContextMenu(null);
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [contextMenu]);

  const activeTitle = useMemo(() => {
    return conversations.data?.find((c) => c.id === activeId)?.title ?? "New chat";
  }, [conversations.data, activeId]);

  const createChat = useMutation({
    mutationFn: () => api.createAdvisorConversation("New chat"),
    onSuccess: (conv) => {
      qc.invalidateQueries({ queryKey: ["advisorConversations"] });
      setActiveId(conv.id);
      setLocalMessages([]);
      setError("");
      setNotice("");
      setEditingId(null);
      setTimeout(() => inputRef.current?.focus(), 50);
    },
  });

  const deleteChat = useMutation({
    mutationFn: (id: number) => api.deleteAdvisorConversation(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["advisorConversations"] });
      if (activeId === id) {
        const remaining = (conversations.data ?? []).filter((c) => c.id !== id);
        setActiveId(remaining[0]?.id ?? null);
        setLocalMessages([]);
        setEditingId(null);
      }
      if (renamingId === id) setRenamingId(null);
    },
  });

  const renameChat = useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) =>
      api.renameAdvisorConversation(id, title),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["advisorConversations"] });
      setRenamingId(null);
      setRenameDraft("");
    },
    onError: (e) => {
      setError((e as Error).message);
    },
  });

  const applyChatResult = async (data: {
    conversation_id: number;
    reply: string;
    message_id?: number;
    compacted?: boolean;
    forked?: boolean;
  }) => {
    setActiveId(data.conversation_id);
    if (data.forked) {
      setNotice("Forked into a new chat from that point.");
    } else if (data.compacted) {
      setNotice("Earlier turns were compacted into memory to keep context efficient.");
    } else {
      setNotice("");
    }
    await qc.invalidateQueries({ queryKey: ["advisorConversations"] });
    await qc.invalidateQueries({ queryKey: ["advisorMessages", data.conversation_id] });
  };

  const startRename = (id: number, currentTitle: string) => {
    setContextMenu(null);
    setRenamingId(id);
    setRenameDraft(currentTitle || "New chat");
  };

  const commitRename = () => {
    if (renamingId == null) return;
    const trimmed = renameDraft.trim();
    if (!trimmed) {
      setRenamingId(null);
      return;
    }
    const current = conversations.data?.find((c) => c.id === renamingId)?.title;
    if (trimmed === current) {
      setRenamingId(null);
      return;
    }
    renameChat.mutate({ id: renamingId, title: trimmed });
  };

  const send = async () => {
    const trimmed = message.trim();
    if (!trimmed || sending) return;
    setSending(true);
    setError("");
    setNotice("");
    setEditingId(null);
    setMessage("");
    setLocalMessages((prev) => [
      ...prev,
      { role: "user", content: trimmed },
      { role: "assistant", content: "Thinking…", pending: true },
    ]);

    try {
      let cid = activeId;
      if (cid == null) {
        const conv = await api.createAdvisorConversation("New chat");
        cid = conv.id;
        setActiveId(cid);
      }
      const data = await api.advisorChat(trimmed, cid);
      setActiveId(data.conversation_id);
      setLocalMessages((prev) => {
        const withoutPending = prev.filter((m) => !m.pending);
        const hasUser = withoutPending.some(
          (m) => m.role === "user" && m.content === trimmed
        );
        const base = hasUser
          ? withoutPending
          : [...withoutPending, { role: "user", content: trimmed }];
        return [
          ...base.filter((m) => !(m.role === "assistant" && m.content === "Thinking…")),
          { id: data.message_id, role: "assistant", content: data.reply },
        ];
      });
      if (data.compacted) {
        setNotice("Earlier turns were compacted into memory to keep context efficient.");
      }
      await qc.invalidateQueries({ queryKey: ["advisorConversations"] });
      await qc.invalidateQueries({ queryKey: ["advisorMessages", data.conversation_id] });
    } catch (e) {
      setLocalMessages((prev) => prev.filter((m) => !m.pending));
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  const startEdit = (m: ChatMessage) => {
    if (!m.id || m.role !== "user" || sending) return;
    setEditingId(m.id);
    setEditDraft(m.content);
    setError("");
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditDraft("");
  };

  const submitEdit = async (fork: boolean) => {
    if (activeId == null || editingId == null || sending) return;
    const trimmed = editDraft.trim();
    if (!trimmed) return;

    const editIndex = localMessages.findIndex((m) => m.id === editingId);
    const messageId = editingId;
    setSending(true);
    setError("");
    setNotice("");
    setEditingId(null);

    if (!fork && editIndex >= 0) {
      setLocalMessages((prev) => [
        ...prev.slice(0, editIndex),
        { id: messageId, role: "user", content: trimmed },
        { role: "assistant", content: "Thinking…", pending: true },
      ]);
    }

    try {
      const data = await api.editAdvisorMessage(activeId, messageId, trimmed, fork);
      if (fork) {
        setLocalMessages([]);
        await applyChatResult(data);
      } else {
        setLocalMessages((prev) => {
          const kept =
            editIndex >= 0
              ? prev.slice(0, editIndex)
              : prev.filter((m) => !m.pending && m.id !== messageId);
          return [
            ...kept,
            { id: messageId, role: "user", content: trimmed },
            { id: data.message_id, role: "assistant", content: data.reply },
          ];
        });
        await applyChatResult(data);
      }
    } catch (e) {
      setLocalMessages((prev) => prev.filter((m) => !m.pending));
      setError((e as Error).message);
      await qc.invalidateQueries({ queryKey: ["advisorMessages", activeId] });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="-mx-8 -mt-2 flex h-[calc(100vh-3.5rem)] min-h-0 overflow-hidden">
      <aside className="flex w-64 shrink-0 flex-col border-r border-surface-border bg-surface-raised">
        <div className="border-b border-surface-border p-3">
          <Button
            size="sm"
            className="w-full justify-start gap-2"
            onClick={() => createChat.mutate()}
            disabled={createChat.isPending}
          >
            <MessageSquarePlus className="h-4 w-4" />
            New chat
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {(conversations.data ?? []).map((c) => (
            <div
              key={c.id}
              className={cn(
                "group mb-0.5 flex items-center gap-1 rounded-lg px-2 py-2 text-sm",
                activeId === c.id
                  ? "bg-accent-soft text-accent"
                  : "text-slate-300 hover:bg-surface-overlay"
              )}
              onContextMenu={(e) => {
                e.preventDefault();
                setContextMenu({
                  conversationId: c.id,
                  x: e.clientX,
                  y: e.clientY,
                });
              }}
            >
              {renamingId === c.id ? (
                <input
                  ref={renameInputRef}
                  value={renameDraft}
                  onChange={(e) => setRenameDraft(e.target.value)}
                  onBlur={() => commitRename()}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      commitRename();
                    } else if (e.key === "Escape") {
                      e.preventDefault();
                      setRenamingId(null);
                      setRenameDraft("");
                    }
                  }}
                  maxLength={120}
                  disabled={renameChat.isPending}
                  className="min-w-0 flex-1 rounded border border-accent/50 bg-surface px-1.5 py-0.5 text-sm text-white outline-none"
                />
              ) : (
                <button
                  type="button"
                  className="min-w-0 flex-1 truncate text-left"
                  onClick={() => {
                    setActiveId(c.id);
                    setError("");
                    setNotice("");
                    setEditingId(null);
                    setContextMenu(null);
                  }}
                  onDoubleClick={(e) => {
                    e.preventDefault();
                    startRename(c.id, c.title || "New chat");
                  }}
                >
                  {c.title || "New chat"}
                </button>
              )}
              <button
                type="button"
                className="shrink-0 rounded p-1 text-muted opacity-0 hover:bg-surface-border hover:text-rose-400 group-hover:opacity-100"
                title="Delete chat"
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm("Delete this chat?")) deleteChat.mutate(c.id);
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
          {!conversations.data?.length && (
            <p className="px-2 py-4 text-xs text-muted">No chats yet — start a new one.</p>
          )}
        </div>
      </aside>

      {contextMenu && (
        <div
          ref={contextMenuRef}
          className="fixed z-50 min-w-[140px] rounded-lg border border-surface-border bg-surface-raised py-1 shadow-xl"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          role="menu"
        >
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-slate-200 hover:bg-surface-overlay"
            role="menuitem"
            onClick={() => {
              const conv = conversations.data?.find((c) => c.id === contextMenu.conversationId);
              startRename(contextMenu.conversationId, conv?.title || "New chat");
            }}
          >
            <Pencil className="h-3.5 w-3.5" />
            Rename
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-rose-400 hover:bg-surface-overlay"
            role="menuitem"
            onClick={() => {
              const id = contextMenu.conversationId;
              setContextMenu(null);
              if (confirm("Delete this chat?")) deleteChat.mutate(id);
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </button>
        </div>
      )}

      <section className="flex min-w-0 flex-1 flex-col bg-surface">
        <header className="flex h-12 items-center border-b border-surface-border px-5">
          <h1 className="truncate text-sm font-medium text-white">{activeTitle}</h1>
          <span className="ml-3 text-[10px] uppercase tracking-wide text-muted">
            Local Ollama
          </span>
        </header>

        <div className="flex-1 overflow-y-auto">
          {localMessages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center px-6 text-center">
              <h2 className="text-2xl font-semibold text-white">Financial advisor</h2>
              <p className="mt-2 max-w-md text-sm text-muted">
                Ask about goals, balances, or how to set up the app. Numbers come from your ledger
                via tools — not invented. Requires local Ollama.
              </p>
              <div className="mt-6 flex max-w-lg flex-wrap justify-center gap-2">
                {[
                  "How do I connect my bank with Plaid?",
                  "How do I back up to Google Drive?",
                  "Am I on track for my investing goal?",
                  "How do I install Ollama for the advisor?",
                ].map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    className="rounded-full border border-surface-border bg-surface-raised px-3 py-1.5 text-left text-xs text-slate-200 hover:border-accent/50 hover:text-white"
                    onClick={() => {
                      setMessage(prompt);
                      inputRef.current?.focus();
                    }}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto w-full max-w-3xl space-y-4 px-4 py-6">
              {localMessages.map((m, i) => {
                if (m.role === "summary") {
                  return (
                    <div
                      key={m.id ?? `summary-${i}`}
                      className="rounded-xl border border-dashed border-surface-border bg-surface-raised/60 px-4 py-3 text-xs leading-relaxed text-muted"
                    >
                      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-accent">
                        Compacted memory
                      </div>
                      <div className="whitespace-pre-wrap">{m.content}</div>
                    </div>
                  );
                }

                const isEditing = editingId != null && m.id === editingId;

                return (
                  <div
                    key={m.id ?? `${m.role}-${i}-${m.content.slice(0, 12)}`}
                    className={cn(
                      "group relative rounded-2xl px-4 py-3 text-sm leading-relaxed",
                      m.role === "user"
                        ? "ml-12 bg-accent/20 text-slate-100"
                        : "mr-8 bg-surface-overlay text-slate-200",
                      m.pending && "animate-pulse text-muted"
                    )}
                  >
                    {isEditing ? (
                      <div className="space-y-2">
                        <textarea
                          value={editDraft}
                          onChange={(e) => setEditDraft(e.target.value)}
                          rows={4}
                          className="w-full resize-y rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-slate-100 outline-none focus:border-accent"
                          disabled={sending}
                          autoFocus
                        />
                        <div className="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            disabled={sending || !editDraft.trim()}
                            onClick={() => void submitEdit(false)}
                          >
                            Save & regenerate
                          </Button>
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={sending || !editDraft.trim()}
                            onClick={() => void submitEdit(true)}
                          >
                            <GitFork className="mr-1 h-3.5 w-3.5" />
                            Fork to new chat
                          </Button>
                          <Button size="sm" variant="ghost" disabled={sending} onClick={cancelEdit}>
                            Cancel
                          </Button>
                        </div>
                        <p className="text-[11px] text-muted">
                          Save drops later messages and reverts agent context to this point. Fork
                          keeps the original chat and continues in a new one.
                        </p>
                      </div>
                    ) : (
                      <>
                        <div className="whitespace-pre-wrap">{m.content}</div>
                        {m.role === "user" && m.id != null && !sending && (
                          <button
                            type="button"
                            className="absolute -left-9 top-2 rounded p-1.5 text-muted opacity-0 hover:bg-surface-overlay hover:text-slate-200 group-hover:opacity-100"
                            title="Edit message"
                            onClick={() => startEdit(m)}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </>
                    )}
                  </div>
                );
              })}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <div className="border-t border-surface-border px-4 py-4">
          <form
            className="mx-auto flex w-full max-w-3xl gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <Input
              ref={inputRef}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Message the advisor…"
              className="flex-1"
              disabled={sending || editingId != null}
            />
            <Button type="submit" disabled={sending || editingId != null || !message.trim()}>
              <Send className="h-4 w-4" />
            </Button>
          </form>
          {notice && <p className="mx-auto mt-2 max-w-3xl text-xs text-accent">{notice}</p>}
          {error && <p className="mx-auto mt-2 max-w-3xl text-xs text-rose-400">{error}</p>}
        </div>
      </section>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageCircle, X } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { Button, Input } from "../ui";

type Props = {
  pageContext?: Record<string, unknown>;
};

export default function AdvisorDrawer({ pageContext }: Props) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const qc = useQueryClient();

  const history = useQuery({
    queryKey: ["advisorMessages", conversationId],
    queryFn: () => api.advisorConversationMessages(conversationId!),
    enabled: open && conversationId != null,
  });

  useEffect(() => {
    if (!open || conversationId != null) return;
    api
      .advisorConversations()
      .then((list) => {
        if (list[0]) setConversationId(list[0].id);
      })
      .catch(() => undefined);
  }, [open, conversationId]);

  const chat = useMutation({
    mutationFn: async (msg: string) => {
      let cid = conversationId;
      if (cid == null) {
        const conv = await api.createAdvisorConversation("Drawer chat");
        cid = conv.id;
        setConversationId(cid);
      }
      return api.advisorChat(msg, cid, pageContext);
    },
    onSuccess: (data) => {
      setConversationId(data.conversation_id);
      qc.invalidateQueries({ queryKey: ["advisorConversations"] });
      qc.invalidateQueries({ queryKey: ["advisorMessages", data.conversation_id] });
      setMessage("");
      setError("");
    },
    onError: (e) => setError((e as Error).message),
  });

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-accent text-white shadow-lg"
        aria-label="Open advisor"
      >
        <MessageCircle className="h-5 w-5" />
      </button>
      {open && (
        <div className="fixed inset-y-0 right-0 z-50 flex w-96 flex-col border-l border-surface-border bg-surface-raised shadow-xl">
          <div className="flex items-center justify-between border-b border-surface-border px-4 py-3">
            <div>
              <span className="text-sm font-medium text-white">Advisor</span>
              <Link to="/advisor" className="ml-2 text-[10px] text-accent hover:underline">
                Open full page
              </Link>
            </div>
            <button type="button" onClick={() => setOpen(false)} className="text-muted hover:text-white">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex-1 space-y-2 overflow-y-auto p-4 text-sm">
            {(history.data ?? []).slice(-20).map((m) => (
              <div
                key={m.id}
                className={`whitespace-pre-wrap rounded px-2 py-1 ${
                  m.role === "user" ? "bg-accent/20" : "bg-surface-overlay text-muted"
                }`}
              >
                {m.content}
              </div>
            ))}
            {chat.isPending && <p className="text-xs text-muted animate-pulse">Thinking…</p>}
            {error && <p className="text-xs text-rose-400">{error}</p>}
          </div>
          <form
            className="flex gap-2 border-t border-surface-border p-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (message.trim()) chat.mutate(message.trim());
            }}
          >
            <Input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Ask…"
              className="flex-1 text-sm"
              disabled={chat.isPending}
            />
            <Button type="submit" size="sm" disabled={chat.isPending || !message.trim()}>
              Send
            </Button>
          </form>
        </div>
      )}
    </>
  );
}

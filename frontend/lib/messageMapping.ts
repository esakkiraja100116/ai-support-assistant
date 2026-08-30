import { ChatUIMessage, PersistedMessage } from "./types";

export function persistedToUIMessages(messages: PersistedMessage[]): ChatUIMessage[] {
  return messages.map((m, i) => {
    if (m.role === "user") {
      return { id: m.id, role: "user", status: "sent", text: m.content };
    }
    // Explain/track turns persist their synthetic question ("What can you
    // tell me about transaction txn_1?") as the preceding user message, so
    // resending it as a plain chat message re-routes to the same intent -
    // reconstructing the original selection isn't otherwise possible from
    // persisted history alone.
    const precedingUser = messages[i - 1];
    const retry: ChatUIMessage["retry"] =
      m.response_type === "ERROR" && precedingUser?.role === "user"
        ? { kind: "chat", message: precedingUser.content }
        : undefined;
    return {
      id: m.id,
      role: "assistant",
      status: "sent",
      text: m.content,
      response: {
        type: m.response_type || "TEXT_ANSWER",
        message: m.content,
        data: m.response_data,
      },
      retry,
    };
  });
}

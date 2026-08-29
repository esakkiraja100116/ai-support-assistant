import { ChatUIMessage, PersistedMessage } from "./types";

export function persistedToUIMessages(messages: PersistedMessage[]): ChatUIMessage[] {
  return messages.map((m) => {
    if (m.role === "user") {
      return { id: m.id, role: "user", status: "sent", text: m.content };
    }
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
    };
  });
}

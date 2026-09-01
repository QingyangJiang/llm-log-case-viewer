export type ApiProtocol = "openai" | "anthropic";
export type ModelApiMessage = { role: "user" | "assistant"; content: string };

type ModelApiRequestInput = {
  protocol: ApiProtocol;
  apiKey: string;
  model: string;
  maxOutputTokens: number;
  systemPrompt: string;
  userContent?: string;
  messages?: ModelApiMessage[];
};

export function cleanApiBaseUrl(baseUrl: string) {
  return baseUrl.trim().replace(/[；;，,。．、]+$/u, "").trim().replace(/\/+$/, "");
}

export function modelApiEndpoint(baseUrl: string, protocol: ApiProtocol) {
  const clean = cleanApiBaseUrl(baseUrl).replace(/\/(?:chat\/completions|messages)$/i, "");
  return protocol === "anthropic" ? `${clean}/messages` : `${clean}/chat/completions`;
}

export function modelApiRequest({ protocol, apiKey, model, maxOutputTokens, systemPrompt, userContent = "", messages }: ModelApiRequestInput) {
  const key = apiKey.trim();
  const rawConversation = messages?.length ? messages : [{ role: "user" as const, content: userContent }];
  const conversation = rawConversation.reduce<ModelApiMessage[]>((result, message) => {
    const previous = result[result.length - 1];
    if (previous?.role === message.role) previous.content = `${previous.content}\n\n${message.content}`;
    else result.push({ ...message });
    return result;
  }, []);
  if (protocol === "anthropic") {
    return {
      headers: { "Content-Type": "application/json", "anthropic-version": "2023-06-01", ...(key ? { "x-api-key": key } : {}) },
      body: JSON.stringify({ model: model.trim(), temperature: 0.2, max_tokens: maxOutputTokens, system: systemPrompt, messages: conversation }),
    };
  }
  return {
    headers: { "Content-Type": "application/json", ...(key ? { Authorization: `Bearer ${key}` } : {}) },
    body: JSON.stringify({ model: model.trim(), temperature: 0.2, max_tokens: maxOutputTokens, stream: false, messages: [{ role: "system", content: systemPrompt }, ...conversation] }),
  };
}

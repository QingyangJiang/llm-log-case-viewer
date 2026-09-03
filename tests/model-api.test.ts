import assert from "node:assert/strict";
import test from "node:test";

import { cleanApiBaseUrl, modelApiEndpoint, modelApiRequest } from "../app/model-api.ts";

test("cleans pasted punctuation and builds protocol-specific endpoints", () => {
  assert.equal(cleanApiBaseUrl(" https://model.nioint.com/token-x/v1； "), "https://model.nioint.com/token-x/v1");
  assert.equal(modelApiEndpoint("https://model.nioint.com/token-x/v1；", "anthropic"), "https://model.nioint.com/token-x/v1/messages");
  assert.equal(modelApiEndpoint("https://example.com/v1/messages", "openai"), "https://example.com/v1/chat/completions");
});

test("builds Anthropic Messages headers and body", () => {
  const request = modelApiRequest({ protocol: "anthropic", apiKey: " secret ", model: "DeepSeek-V4-Flash", maxOutputTokens: 1024, systemPrompt: "system", userContent: "hello" });
  assert.deepEqual(request.headers, { "Content-Type": "application/json", "anthropic-version": "2023-06-01", "x-api-key": "secret" });
  assert.deepEqual(JSON.parse(request.body), {
    model: "DeepSeek-V4-Flash",
    temperature: 0.2,
    max_tokens: 1024,
    system: "system",
    messages: [{ role: "user", content: "hello" }],
  });
});

test("keeps the existing OpenAI-compatible request shape", () => {
  const request = modelApiRequest({ protocol: "openai", apiKey: "sk-test", model: "model-a", maxOutputTokens: 512, systemPrompt: "system", userContent: "hello" });
  assert.equal(request.headers.Authorization, "Bearer sk-test");
  assert.deepEqual(JSON.parse(request.body).messages, [{ role: "system", content: "system" }, { role: "user", content: "hello" }]);
});

test("allows judge requests to override temperature and seed", () => {
  const request = modelApiRequest({ protocol: "openai", apiKey: "key", model: "judge", maxOutputTokens: 4096, temperature: 0.1, seed: 7, systemPrompt: "judge", userContent: "case" });
  const body = JSON.parse(request.body);
  assert.equal(body.temperature, 0.1);
  assert.equal(body.seed, 7);
});

test("preserves multi-turn chat history for both protocols", () => {
  const messages = [{ role: "user" as const, content: "问题一" }, { role: "assistant" as const, content: "回答一" }, { role: "user" as const, content: "继续" }];
  const anthropic = modelApiRequest({ protocol: "anthropic", apiKey: "key", model: "model-a", maxOutputTokens: 256, systemPrompt: "system", messages });
  const openai = modelApiRequest({ protocol: "openai", apiKey: "key", model: "model-a", maxOutputTokens: 256, systemPrompt: "system", messages });
  assert.deepEqual(JSON.parse(anthropic.body).messages, messages);
  assert.deepEqual(JSON.parse(openai.body).messages, [{ role: "system", content: "system" }, ...messages]);
});

"use client";

import { ChangeEvent, DragEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";

type JsonObject = Record<string, unknown>;
type LogCase = JsonObject & {
  id?: string | number;
  model?: string;
  messages?: JsonObject[];
  tools?: JsonObject[];
  __line?: number;
};

type Protocol = "openai" | "anthropic" | "unknown";
type ViewTab = "conversation" | "tools" | "raw";

const SAMPLE_CASES: LogCase[] = [
  {
    id: "case-openai-001",
    model: "gpt-5.4",
    tools: [
      {
        type: "function",
        function: {
          name: "search_docs",
          description: "Search company documents",
          parameters: {
            type: "object",
            properties: { query: { type: "string" }, top_k: { type: "integer" } },
            required: ["query"],
          },
        },
      },
    ],
    messages: [
      { role: "system", content: "You are an enterprise knowledge assistant. Cite the source document." },
      { role: "user", content: "今年的年假政策是什么？" },
      {
        role: "assistant",
        content: null,
        tool_calls: [
          {
            id: "call_9f2a",
            type: "function",
            function: { name: "search_docs", arguments: '{"query":"2026 年假政策","top_k":3}' },
          },
        ],
      },
      {
        role: "tool",
        tool_call_id: "call_9f2a",
        content: '{"title":"员工休假管理办法","annual_leave":"5–15 天，按累计工龄计算"}',
      },
      { role: "assistant", content: "根据《员工休假管理办法》，年假为 5–15 天，具体天数按累计工龄计算。" },
    ],
  },
  {
    id: "case-anthropic-002",
    model: "claude-sonnet-4-5",
    tools: [
      {
        name: "get_vehicle_status",
        description: "Read the latest vehicle diagnostic status",
        input_schema: {
          type: "object",
          properties: { vin: { type: "string" } },
          required: ["vin"],
        },
      },
    ],
    messages: [
      { role: "user", content: [{ type: "text", text: "检查车辆 NIO-TEST-001 的当前状态" }] },
      {
        role: "assistant",
        content: [
          { type: "thinking", thinking: "I should retrieve the latest diagnostic status." },
          { type: "tool_use", id: "toolu_01", name: "get_vehicle_status", input: { vin: "NIO-TEST-001" } },
        ],
      },
      {
        role: "user",
        content: [
          { type: "tool_result", tool_use_id: "toolu_01", content: "Battery 82%; no active fault codes." },
        ],
      },
      { role: "assistant", content: [{ type: "text", text: "车辆电量 82%，当前没有活跃故障码。" }] },
    ],
  },
  {
    id: "case-multimodal-003",
    model: "gpt-4.1",
    messages: [
      {
        role: "user",
        content: [
          { type: "input_text", text: "描述这张图中的主要问题" },
          { type: "image_url", image_url: { url: "https://example.invalid/redacted-image.jpg" } },
        ],
      },
      { role: "assistant", content: "图片引用已识别，但示例中未加载外部图像。" },
    ],
    tools: [],
  },
];

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function detectProtocol(item: LogCase): Protocol {
  const tools = Array.isArray(item.tools) ? item.tools : [];
  const messages = Array.isArray(item.messages) ? item.messages : [];
  if (tools.some((tool) => isObject(tool) && "input_schema" in tool)) return "anthropic";
  if (tools.some((tool) => isObject(tool) && tool.type === "function" && isObject(tool.function))) return "openai";
  for (const message of messages) {
    if (Array.isArray(message.content)) {
      const types = message.content.filter(isObject).map((block) => String(block.type ?? ""));
      if (types.some((type) => ["tool_use", "tool_result", "thinking"].includes(type))) return "anthropic";
      if (types.some((type) => ["image_url", "input_text", "input_image"].includes(type))) return "openai";
    }
    if (Array.isArray(message.tool_calls) || "tool_call_id" in message) return "openai";
  }
  return "unknown";
}

function protocolLabel(protocol: Protocol) {
  return protocol === "openai" ? "OpenAI" : protocol === "anthropic" ? "Anthropic" : "通用";
}

function stringify(value: unknown, spaces = 2) {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  try {
    return JSON.stringify(value, null, spaces);
  } catch {
    return String(value);
  }
}

function tryPrettyJson(value: unknown) {
  if (typeof value !== "string") return stringify(value);
  const trimmed = value.trim();
  if (!trimmed || !["{", "["].includes(trimmed[0])) return value;
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

function extractText(value: unknown): string {
  if (typeof value === "string") return value;
  if (!Array.isArray(value)) return stringify(value, 0);
  return value
    .map((block) => {
      if (!isObject(block)) return stringify(block, 0);
      if (typeof block.text === "string") return block.text;
      if (typeof block.thinking === "string") return block.thinking;
      if (block.type === "tool_use") return `${String(block.name ?? "tool")} ${stringify(block.input, 0)}`;
      if (block.type === "tool_result") return stringify(block.content, 0);
      if (block.type === "image_url" || block.type === "input_image") return "[image]";
      return stringify(block, 0);
    })
    .join(" ");
}

function getCaseTitle(item: LogCase, index: number) {
  const firstUser = (item.messages ?? []).find((message) => message.role === "user" && extractText(message.content).trim());
  const text = firstUser ? extractText(firstUser.content).replace(/\s+/g, " ").trim() : "无用户消息";
  return text || `Case ${index + 1}`;
}

function getToolCalls(item: LogCase) {
  let count = 0;
  for (const message of item.messages ?? []) {
    if (Array.isArray(message.tool_calls)) count += message.tool_calls.length;
    if (Array.isArray(message.content)) {
      count += message.content.filter((block) => isObject(block) && block.type === "tool_use").length;
    }
  }
  return count;
}

function countCharacters(item: LogCase) {
  return (item.messages ?? []).reduce((sum, message) => sum + extractText(message.content).length, 0);
}

function parseJsonl(text: string) {
  const cases: LogCase[] = [];
  const errors: string[] = [];
  const trimmed = text.trim();
  if (!trimmed) return { cases, errors: ["文件为空"] };

  if (trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed);
      if (!Array.isArray(parsed)) throw new Error("JSON 根节点不是数组");
      parsed.forEach((item, index) => {
        if (isObject(item)) cases.push({ ...item, __line: index + 1 } as LogCase);
        else errors.push(`第 ${index + 1} 项不是 JSON object`);
      });
      return { cases, errors };
    } catch (error) {
      errors.push(`JSON 数组解析失败：${error instanceof Error ? error.message : "未知错误"}`);
      return { cases, errors };
    }
  }

  text.split(/\r?\n/).forEach((line, index) => {
    if (!line.trim()) return;
    try {
      const parsed = JSON.parse(line);
      if (!isObject(parsed)) throw new Error("该行不是 JSON object");
      cases.push({ ...parsed, __line: index + 1 } as LogCase);
    } catch (error) {
      errors.push(`第 ${index + 1} 行：${error instanceof Error ? error.message : "解析失败"}`);
    }
  });
  return { cases, errors };
}

function Icon({ children }: { children: ReactNode }) {
  return <span className="icon" aria-hidden="true">{children}</span>;
}

function JsonCode({ value, compact = false }: { value: unknown; compact?: boolean }) {
  return <pre className={compact ? "json-code compact" : "json-code"}>{tryPrettyJson(value)}</pre>;
}

function ContentBlock({ block }: { block: JsonObject }) {
  const type = String(block.type ?? "content");
  if (["text", "input_text", "output_text"].includes(type)) {
    return <p className="message-text">{String(block.text ?? "")}</p>;
  }
  if (type === "thinking") {
    return (
      <details className="thinking-block">
        <summary>Thinking / Reasoning</summary>
        <p>{String(block.thinking ?? block.text ?? "")}</p>
      </details>
    );
  }
  if (type === "tool_use") {
    return (
      <div className="tool-block">
        <div className="tool-block-head"><span>TOOL USE</span><strong>{String(block.name ?? "unnamed_tool")}</strong></div>
        <JsonCode value={block.input ?? {}} compact />
        {block.id ? <code className="call-id">{String(block.id)}</code> : null}
      </div>
    );
  }
  if (type === "tool_result") {
    return (
      <div className="tool-block result">
        <div className="tool-block-head"><span>TOOL RESULT</span><code>{String(block.tool_use_id ?? "")}</code></div>
        <JsonCode value={block.content ?? block} compact />
      </div>
    );
  }
  if (["image_url", "input_image", "image"].includes(type)) {
    const source = isObject(block.image_url) ? block.image_url.url : block.image_url ?? block.source ?? "image";
    return (
      <div className="media-block">
        <Icon>▧</Icon><div><strong>图片内容</strong><code>{typeof source === "string" ? source : stringify(source, 0)}</code></div>
      </div>
    );
  }
  return (
    <div className="unknown-block">
      <span className="mini-label">{type}</span>
      <JsonCode value={block} compact />
    </div>
  );
}

function MessageCard({ message, index }: { message: JsonObject; index: number }) {
  const role = String(message.role ?? "unknown");
  const content = message.content;
  const roleNames: Record<string, string> = { system: "SYSTEM", user: "USER", assistant: "ASSISTANT", tool: "TOOL", developer: "DEVELOPER" };
  const blocks = Array.isArray(content) ? content : null;
  const toolCalls = Array.isArray(message.tool_calls) ? message.tool_calls.filter(isObject) : [];

  return (
    <article className={`message-card role-${role}`}>
      <header className="message-head">
        <div className="role-wrap"><span className="role-dot" /><strong>{roleNames[role] ?? role.toUpperCase()}</strong></div>
        <span className="message-index">#{index + 1}</span>
      </header>
      <div className="message-body">
        {typeof content === "string" ? <p className="message-text">{content}</p> : null}
        {content !== undefined && content !== null && !blocks && typeof content !== "string" ? <JsonCode value={content} compact /> : null}
        {blocks?.map((block, blockIndex) =>
          isObject(block) ? <ContentBlock key={blockIndex} block={block} /> : <JsonCode key={blockIndex} value={block} compact />,
        )}
        {content === null && !toolCalls.length ? <p className="empty-content">content: null</p> : null}
        {toolCalls.map((call, callIndex) => {
          const fn = isObject(call.function) ? call.function : call;
          return (
            <div className="tool-block" key={callIndex}>
              <div className="tool-block-head"><span>TOOL CALL</span><strong>{String(fn.name ?? "unnamed_tool")}</strong></div>
              <JsonCode value={tryPrettyJson(fn.arguments ?? call.input ?? {})} compact />
              {call.id ? <code className="call-id">{String(call.id)}</code> : null}
            </div>
          );
        })}
        {role === "tool" && message.tool_call_id ? (
          <div className="tool-link">响应调用 <code>{String(message.tool_call_id)}</code></div>
        ) : null}
      </div>
    </article>
  );
}

function ToolDefinition({ tool, index, protocol }: { tool: JsonObject; index: number; protocol: Protocol }) {
  const fn = protocol === "openai" && isObject(tool.function) ? tool.function : tool;
  const schema = fn.parameters ?? fn.input_schema ?? {};
  return (
    <article className="definition-card">
      <div className="definition-index">{String(index + 1).padStart(2, "0")}</div>
      <div className="definition-main">
        <div className="definition-title"><strong>{String(fn.name ?? "unnamed_tool")}</strong><span>{protocolLabel(protocol)}</span></div>
        {fn.description ? <p>{String(fn.description)}</p> : <p className="muted">无 description</p>}
        <details><summary>查看 Schema</summary><JsonCode value={schema} /></details>
      </div>
    </article>
  );
}

export default function Home() {
  const [cases, setCases] = useState<LogCase[]>(SAMPLE_CASES);
  const [fileName, setFileName] = useState("内置示例 · sample.jsonl");
  const [selectedKey, setSelectedKey] = useState("0");
  const [query, setQuery] = useState("");
  const [protocolFilter, setProtocolFilter] = useState<"all" | Protocol>("all");
  const [modelFilter, setModelFilter] = useState("all");
  const [tab, setTab] = useState<ViewTab>("conversation");
  const [dragging, setDragging] = useState(false);
  const [parseErrors, setParseErrors] = useState<string[]>([]);
  const [notice, setNotice] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const models = useMemo(() => Array.from(new Set(cases.map((item) => item.model).filter(Boolean) as string[])).sort(), [cases]);
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return cases
      .map((item, index) => ({ item, index, protocol: detectProtocol(item) }))
      .filter(({ item, protocol }) => protocolFilter === "all" || protocol === protocolFilter)
      .filter(({ item }) => modelFilter === "all" || item.model === modelFilter)
      .filter(({ item }) => {
        if (!normalized) return true;
        const searchable = [item.id, item.model, ...(item.messages ?? []).map((message) => extractText(message.content))].join(" ").toLowerCase();
        return searchable.includes(normalized);
      });
  }, [cases, query, protocolFilter, modelFilter]);

  const selectedPair = filtered.find(({ index }) => String(index) === selectedKey) ?? filtered[0];
  const selected = selectedPair?.item;
  const selectedProtocol = selected ? detectProtocol(selected) : "unknown";

  useEffect(() => {
    const handleKeys = (event: KeyboardEvent) => {
      if (["INPUT", "TEXTAREA", "SELECT"].includes((event.target as HTMLElement)?.tagName)) return;
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      event.preventDefault();
      const currentPosition = Math.max(0, filtered.findIndex(({ index }) => String(index) === selectedKey));
      const nextPosition = event.key === "ArrowDown" ? Math.min(filtered.length - 1, currentPosition + 1) : Math.max(0, currentPosition - 1);
      const next = filtered[nextPosition];
      if (next) setSelectedKey(String(next.index));
    };
    window.addEventListener("keydown", handleKeys);
    return () => window.removeEventListener("keydown", handleKeys);
  }, [filtered, selectedKey]);

  const loadText = (text: string, name: string) => {
    const parsed = parseJsonl(text);
    setParseErrors(parsed.errors);
    if (parsed.cases.length) {
      setCases(parsed.cases);
      setFileName(name);
      setSelectedKey("0");
      setQuery("");
      setProtocolFilter("all");
      setModelFilter("all");
      setTab("conversation");
      setNotice(`已在本地载入 ${parsed.cases.length.toLocaleString()} 条 case`);
      window.setTimeout(() => setNotice(""), 2600);
    }
  };

  const loadFile = async (file?: File) => {
    if (!file) return;
    const text = await file.text();
    loadText(text, file.name);
  };

  const onDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    setDragging(false);
    void loadFile(event.dataTransfer.files?.[0]);
  };

  const copySelected = async () => {
    if (!selected) return;
    await navigator.clipboard.writeText(JSON.stringify(selected, (key, value) => key === "__line" ? undefined : value, 2));
    setNotice("已复制当前 Case JSON");
    window.setTimeout(() => setNotice(""), 1800);
  };

  const exportSelected = () => {
    if (!selected) return;
    const clean = { ...selected };
    delete clean.__line;
    const blob = new Blob([JSON.stringify(clean, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${String(selected.id ?? "case")}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const totalMessages = cases.reduce((sum, item) => sum + (item.messages?.length ?? 0), 0);
  const totalCalls = cases.reduce((sum, item) => sum + getToolCalls(item), 0);

  return (
    <main
      className={`app-shell ${dragging ? "is-dragging" : ""}`}
      onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => { if (event.currentTarget === event.target) setDragging(false); }}
      onDrop={onDrop}
    >
      <header className="topbar">
        <div className="brand">
          <button className="mobile-menu" onClick={() => setSidebarOpen((open) => !open)} aria-label="打开 Case 列表">☰</button>
          <div className="brand-mark"><span /><span /><span /></div>
          <div><h1>Case Lens</h1><p>LLM LOG EXPLORER</p></div>
        </div>
        <div className="top-actions">
          <span className="privacy-badge"><Icon>●</Icon>日志仅在本地浏览器处理</span>
          <input ref={fileInput} type="file" accept=".jsonl,.json,application/json,text/plain" hidden onChange={(event: ChangeEvent<HTMLInputElement>) => void loadFile(event.target.files?.[0])} />
          <button className="button primary" onClick={() => fileInput.current?.click()}><Icon>＋</Icon>载入 JSONL</button>
        </div>
      </header>

      <section className="stat-strip">
        <div><span>DATASET</span><strong>{fileName}</strong></div>
        <div><span>CASES</span><strong>{cases.length.toLocaleString()}</strong></div>
        <div><span>MESSAGES</span><strong>{totalMessages.toLocaleString()}</strong></div>
        <div><span>TOOL CALLS</span><strong>{totalCalls.toLocaleString()}</strong></div>
        <div className="shortcut-hint"><kbd>↑</kbd><kbd>↓</kbd><span>切换 Case</span></div>
      </section>

      {parseErrors.length ? (
        <details className="error-banner">
          <summary>有 {parseErrors.length} 行未能解析；其余有效 case 已正常载入</summary>
          <ul>{parseErrors.slice(0, 20).map((error, index) => <li key={index}>{error}</li>)}</ul>
        </details>
      ) : null}

      <div className="workspace">
        <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
          <div className="sidebar-tools">
            <label className="search-box"><Icon>⌕</Icon><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 ID、模型或消息…" /><kbd>⌘K</kbd></label>
            <div className="filters">
              <select value={protocolFilter} onChange={(event) => setProtocolFilter(event.target.value as "all" | Protocol)} aria-label="协议筛选">
                <option value="all">全部协议</option><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option><option value="unknown">通用 / 未知</option>
              </select>
              <select value={modelFilter} onChange={(event) => setModelFilter(event.target.value)} aria-label="模型筛选">
                <option value="all">全部模型</option>{models.map((model) => <option value={model} key={model}>{model}</option>)}
              </select>
            </div>
            <div className="result-count"><strong>{filtered.length.toLocaleString()}</strong> 个匹配 Case</div>
          </div>
          <div className="case-list">
            {filtered.map(({ item, index, protocol }) => {
              const active = selectedPair?.index === index;
              return (
                <button className={`case-row ${active ? "active" : ""}`} key={`${String(item.id)}-${index}`} onClick={() => { setSelectedKey(String(index)); setSidebarOpen(false); }}>
                  <div className="case-row-top"><span className={`protocol-dot ${protocol}`} /><code>{String(item.id ?? `case-${index + 1}`)}</code><span className="row-index">{String(index + 1).padStart(3, "0")}</span></div>
                  <p>{getCaseTitle(item, index)}</p>
                  <div className="case-row-meta"><span>{item.model ?? "unknown model"}</span><span>{item.messages?.length ?? 0} msgs</span>{getToolCalls(item) ? <span className="call-count">⌁ {getToolCalls(item)}</span> : null}</div>
                </button>
              );
            })}
            {!filtered.length ? <div className="empty-list"><span>∅</span><p>没有匹配的 Case</p><button onClick={() => { setQuery(""); setProtocolFilter("all"); setModelFilter("all"); }}>清除筛选</button></div> : null}
          </div>
        </aside>

        <section className="detail-panel">
          {selected ? (
            <>
              <div className="detail-header">
                <div>
                  <div className="eyebrow"><span className={`protocol-pill ${selectedProtocol}`}>{protocolLabel(selectedProtocol)}</span><code>{String(selected.id ?? `line-${selected.__line ?? "?"}`)}</code></div>
                  <h2>{getCaseTitle(selected, selectedPair?.index ?? 0)}</h2>
                </div>
                <div className="detail-actions">
                  <button className="icon-button" onClick={copySelected} title="复制 JSON">⧉</button>
                  <button className="icon-button" onClick={exportSelected} title="下载当前 Case">↓</button>
                </div>
              </div>

              <div className="case-facts">
                <div><span>MODEL</span><strong>{selected.model ?? "—"}</strong></div>
                <div><span>MESSAGES</span><strong>{selected.messages?.length ?? 0}</strong></div>
                <div><span>TOOLS</span><strong>{selected.tools?.length ?? 0}</strong></div>
                <div><span>TOOL CALLS</span><strong>{getToolCalls(selected)}</strong></div>
                <div><span>CHARACTERS</span><strong>{countCharacters(selected).toLocaleString()}</strong></div>
                <div><span>SOURCE LINE</span><strong>{selected.__line ?? "—"}</strong></div>
              </div>

              <nav className="tabs" aria-label="Case 视图">
                <button className={tab === "conversation" ? "active" : ""} onClick={() => setTab("conversation")}>对话轨迹 <span>{selected.messages?.length ?? 0}</span></button>
                <button className={tab === "tools" ? "active" : ""} onClick={() => setTab("tools")}>Tools 定义 <span>{selected.tools?.length ?? 0}</span></button>
                <button className={tab === "raw" ? "active" : ""} onClick={() => setTab("raw")}>原始 JSON</button>
              </nav>

              <div className="tab-content">
                {tab === "conversation" ? (
                  <div className="conversation">
                    {(selected.messages ?? []).map((message, index) => <MessageCard message={message} index={index} key={index} />)}
                    {!selected.messages?.length ? <div className="empty-panel"><span>≡</span><h3>这个 Case 没有 messages</h3><p>可切到“原始 JSON”检查实际字段结构。</p></div> : null}
                  </div>
                ) : null}
                {tab === "tools" ? (
                  <div className="tool-definitions">
                    {(selected.tools ?? []).map((tool, index) => <ToolDefinition tool={tool} index={index} protocol={selectedProtocol} key={index} />)}
                    {!selected.tools?.length ? <div className="empty-panel"><span>⌁</span><h3>这个 Case 没有 Tools 定义</h3><p>消息中的工具调用仍会显示在对话轨迹中。</p></div> : null}
                  </div>
                ) : null}
                {tab === "raw" ? <div className="raw-panel"><div className="raw-head"><span>CASE.JSON</span><button onClick={copySelected}>复制</button></div><JsonCode value={selected} /></div> : null}
              </div>
            </>
          ) : <div className="empty-panel full"><span>∅</span><h3>没有可显示的 Case</h3><p>调整筛选条件，或载入新的 JSONL 文件。</p></div>}
        </section>
      </div>

      {dragging ? <div className="drop-overlay"><div><span>⇣</span><h2>释放以载入日志</h2><p>支持 .jsonl 与 JSON 数组 · 全程本地解析</p></div></div> : null}
      {notice ? <div className="toast">✓ {notice}</div> : null}
    </main>
  );
}

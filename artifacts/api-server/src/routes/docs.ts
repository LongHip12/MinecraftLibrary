import { Router, type IRouter } from "express";
import { SUPPORTED_MODELS } from "./chat";

const router: IRouter = Router();

router.get("/docs", (_req, res) => {
  const pythonExamples = SUPPORTED_MODELS.map(
    (model) => `# Example using model: ${model}
import requests

response = requests.post(
    "https://your-domain.com/api/v2/chat/ai",
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer YOUR_API_KEY"
    },
    json={
        "model": "${model}",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, how are you?"}
        ],
        "temperature": 0.7,
        "max_tokens": 2048,
        "stream": False
    }
)
print(response.json())`,
  ).join("\n\n" + "─".repeat(60) + "\n\n");

  const modelCards = SUPPORTED_MODELS.map((model) => {
    let provider = "OpenAI";
    let badge = "#10a37f";
    if (model.startsWith("claude")) {
      provider = "Anthropic";
      badge = "#d97706";
    } else if (model.startsWith("gemini")) {
      provider = "Google";
      badge = "#4285f4";
    }
    return `<div class="model-card">
        <span class="model-badge" style="background:${badge}">${provider}</span>
        <code class="model-id">${model}</code>
      </div>`;
  }).join("\n");

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>API Docs — /api/v2/chat/ai</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg: #0f1117;
      --surface: #1a1d27;
      --surface2: #22263a;
      --border: #2e3248;
      --accent: #7c6af7;
      --accent2: #a78bfa;
      --text: #e2e4ef;
      --muted: #8b8fa8;
      --green: #10b981;
      --yellow: #f59e0b;
      --blue: #3b82f6;
      --red: #ef4444;
      --radius: 10px;
      --font-mono: "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;
    }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
      line-height: 1.6;
      min-height: 100vh;
    }

    nav {
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(15,17,23,0.85);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
      padding: 0 24px;
      height: 56px;
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .nav-brand {
      font-weight: 700;
      font-size: 15px;
      color: var(--accent2);
      letter-spacing: -0.3px;
      white-space: nowrap;
    }

    .nav-brand span {
      color: var(--muted);
      font-weight: 400;
    }

    .nav-search-wrap {
      flex: 1;
      max-width: 360px;
      position: relative;
    }

    .nav-search-wrap svg {
      position: absolute;
      left: 10px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--muted);
      pointer-events: none;
    }

    #search {
      width: 100%;
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 7px 12px 7px 34px;
      color: var(--text);
      font-size: 13px;
      outline: none;
      transition: border-color 0.15s;
    }

    #search::placeholder { color: var(--muted); }
    #search:focus { border-color: var(--accent); }

    .nav-spacer { flex: 1; }

    .btn-new-chat {
      display: flex;
      align-items: center;
      gap: 7px;
      background: var(--accent);
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 8px 16px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
      transition: background 0.15s, transform 0.1s;
    }

    .btn-new-chat:hover { background: var(--accent2); transform: translateY(-1px); }
    .btn-new-chat:active { transform: translateY(0); }

    main {
      max-width: 900px;
      margin: 0 auto;
      padding: 48px 24px 80px;
    }

    .page-header {
      margin-bottom: 40px;
    }

    .endpoint-pill {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 50px;
      padding: 6px 16px 6px 10px;
      margin-bottom: 20px;
    }

    .method {
      background: var(--green);
      color: #000;
      font-size: 11px;
      font-weight: 800;
      padding: 2px 8px;
      border-radius: 50px;
      letter-spacing: 0.5px;
    }

    .endpoint-path {
      font-family: var(--font-mono);
      font-size: 14px;
      color: var(--text);
    }

    h1 {
      font-size: 32px;
      font-weight: 800;
      letter-spacing: -0.8px;
      background: linear-gradient(135deg, var(--text) 0%, var(--accent2) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      margin-bottom: 10px;
    }

    .subtitle {
      color: var(--muted);
      font-size: 16px;
    }

    section {
      margin-bottom: 40px;
    }

    h2 {
      font-size: 18px;
      font-weight: 700;
      margin-bottom: 16px;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 8px;
    }

    h2::before {
      content: "";
      display: block;
      width: 3px;
      height: 18px;
      background: var(--accent);
      border-radius: 2px;
    }

    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
    }

    .schema-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13.5px;
    }

    .schema-table th {
      background: var(--surface2);
      padding: 10px 16px;
      text-align: left;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.8px;
      text-transform: uppercase;
      color: var(--muted);
      border-bottom: 1px solid var(--border);
    }

    .schema-table td {
      padding: 12px 16px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }

    .schema-table tr:last-child td { border-bottom: none; }

    .schema-table tr:hover td { background: rgba(124,106,247,0.04); }

    .param-name {
      font-family: var(--font-mono);
      font-size: 13px;
      color: #e879f9;
    }

    .param-type {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--blue);
    }

    .badge-req {
      background: rgba(239,68,68,0.15);
      color: var(--red);
      font-size: 10px;
      font-weight: 700;
      padding: 1px 7px;
      border-radius: 50px;
      letter-spacing: 0.4px;
    }

    .badge-opt {
      background: rgba(139,143,168,0.15);
      color: var(--muted);
      font-size: 10px;
      font-weight: 700;
      padding: 1px 7px;
      border-radius: 50px;
      letter-spacing: 0.4px;
    }

    .models-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 10px;
    }

    .model-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 14px 16px;
      display: flex;
      align-items: center;
      gap: 10px;
      transition: border-color 0.15s;
    }

    .model-card:hover { border-color: var(--accent); }

    .model-badge {
      font-size: 10px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 50px;
      color: #fff;
      white-space: nowrap;
      letter-spacing: 0.3px;
    }

    .model-id {
      font-family: var(--font-mono);
      font-size: 13px;
      color: var(--text);
    }

    .code-block {
      background: #0d0f16;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
    }

    .code-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 16px;
      background: var(--surface2);
      border-bottom: 1px solid var(--border);
      font-size: 12px;
      color: var(--muted);
    }

    .lang-tag {
      display: flex;
      align-items: center;
      gap: 6px;
      font-weight: 600;
      color: #f59e0b;
    }

    .copy-btn {
      background: none;
      border: 1px solid var(--border);
      color: var(--muted);
      font-size: 11px;
      padding: 3px 10px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
    }

    .copy-btn:hover { border-color: var(--accent); color: var(--accent2); }

    pre {
      margin: 0;
      padding: 20px;
      overflow-x: auto;
      font-family: var(--font-mono);
      font-size: 12.5px;
      line-height: 1.7;
      color: #c8d3f5;
      tab-size: 4;
    }

    .tabs {
      display: flex;
      gap: 4px;
      margin-bottom: 16px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0;
    }

    .tab-btn {
      background: none;
      border: none;
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
      padding: 8px 16px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
      transition: all 0.15s;
    }

    .tab-btn.active { color: var(--accent2); border-bottom-color: var(--accent); }
    .tab-btn:hover:not(.active) { color: var(--text); }

    .tab-content { display: none; }
    .tab-content.active { display: block; }

    .env-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .env-item {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 14px 16px;
      display: flex;
      align-items: flex-start;
      gap: 12px;
    }

    .env-key {
      font-family: var(--font-mono);
      font-size: 13px;
      color: #34d399;
      white-space: nowrap;
      min-width: 220px;
    }

    .env-desc {
      font-size: 13px;
      color: var(--muted);
    }

    .env-req-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--red);
      margin-top: 5px;
      flex-shrink: 0;
    }

    .env-opt-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--muted);
      margin-top: 5px;
      flex-shrink: 0;
    }

    .search-highlight {
      background: rgba(124,106,247,0.3);
      border-radius: 2px;
    }

    #no-results {
      display: none;
      text-align: center;
      color: var(--muted);
      padding: 40px;
      font-size: 14px;
    }

    @media (max-width: 600px) {
      .models-grid { grid-template-columns: 1fr; }
      h1 { font-size: 24px; }
      .env-item { flex-direction: column; gap: 6px; }
      .env-key { min-width: unset; }
    }
  </style>
</head>
<body>
  <nav>
    <div class="nav-brand">MinecraftLibrary <span>/ API Docs</span></div>
    <div class="nav-search-wrap">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
      </svg>
      <input id="search" type="text" placeholder="Search conversations, endpoints..." autocomplete="off" />
    </div>
    <div class="nav-spacer"></div>
    <button class="btn-new-chat" onclick="newChat()">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path d="M12 5v14M5 12h14"/>
      </svg>
      Create a new chat
    </button>
  </nav>

  <main id="main-content">
    <div class="page-header">
      <div class="endpoint-pill">
        <span class="method">POST</span>
        <span class="endpoint-path">/api/v2/chat/ai</span>
      </div>
      <h1>AI Chat Endpoint</h1>
      <p class="subtitle">Send messages to any of the 7 supported AI models and receive completions.</p>
    </div>

    <section id="section-request">
      <h2>Request Format</h2>
      <div class="card">
        <table class="schema-table">
          <thead>
            <tr>
              <th>Field</th>
              <th>Type</th>
              <th>Required</th>
              <th>Default</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><span class="param-name">model</span></td>
              <td><span class="param-type">string (enum)</span></td>
              <td><span class="badge-req">required</span></td>
              <td>—</td>
              <td>One of the 7 supported model IDs listed below</td>
            </tr>
            <tr>
              <td><span class="param-name">messages</span></td>
              <td><span class="param-type">array&lt;Message&gt;</span></td>
              <td><span class="badge-req">required</span></td>
              <td>—</td>
              <td>Array of message objects with <code>role</code> (system | user | assistant) and <code>content</code></td>
            </tr>
            <tr>
              <td><span class="param-name">temperature</span></td>
              <td><span class="param-type">float</span></td>
              <td><span class="badge-opt">optional</span></td>
              <td>0.7</td>
              <td>Sampling temperature between 0 (deterministic) and 2 (very random)</td>
            </tr>
            <tr>
              <td><span class="param-name">max_tokens</span></td>
              <td><span class="param-type">integer</span></td>
              <td><span class="badge-opt">optional</span></td>
              <td>2048</td>
              <td>Maximum tokens in the completion. Range: 1–16384</td>
            </tr>
            <tr>
              <td><span class="param-name">stream</span></td>
              <td><span class="param-type">boolean</span></td>
              <td><span class="badge-opt">optional</span></td>
              <td>false</td>
              <td>Whether to stream the response via server-sent events</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section id="section-models">
      <h2>Supported Models (7)</h2>
      <div class="models-grid">
        ${modelCards}
      </div>
    </section>

    <section id="section-env">
      <h2>Required Environment Variables</h2>
      <div class="env-list">
        <div class="env-item">
          <div class="env-req-dot"></div>
          <div class="env-key">DATABASE_URL</div>
          <div class="env-desc">PostgreSQL connection string. Used by Drizzle ORM to persist chat history and users.</div>
        </div>
        <div class="env-item">
          <div class="env-req-dot"></div>
          <div class="env-key">OPENAI_API_KEY</div>
          <div class="env-desc">OpenAI secret key. Required for gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo.</div>
        </div>
        <div class="env-item">
          <div class="env-req-dot"></div>
          <div class="env-key">ANTHROPIC_API_KEY</div>
          <div class="env-desc">Anthropic secret key. Required for claude-3-5-sonnet-20241022, claude-3-haiku-20240307.</div>
        </div>
        <div class="env-item">
          <div class="env-req-dot"></div>
          <div class="env-key">GOOGLE_AI_API_KEY</div>
          <div class="env-desc">Google AI (Gemini) API key. Required for gemini-1.5-pro.</div>
        </div>
        <div class="env-item">
          <div class="env-req-dot"></div>
          <div class="env-key">SESSION_SECRET</div>
          <div class="env-desc">Secret used to sign session cookies. Use a long random string (32+ chars).</div>
        </div>
        <div class="env-item">
          <div class="env-opt-dot"></div>
          <div class="env-key">PORT</div>
          <div class="env-desc">Port for the Express server. Defaults to 5000 in dev. Set automatically by Replit in production.</div>
        </div>
        <div class="env-item">
          <div class="env-opt-dot"></div>
          <div class="env-key">NODE_ENV</div>
          <div class="env-desc">Set to <code>production</code> in deployed environments. Controls logging, error details, and caching.</div>
        </div>
      </div>
    </section>

    <section id="section-examples">
      <h2>Python Examples</h2>
      <div class="tabs">
        ${SUPPORTED_MODELS.map((m, i) => `<button class="tab-btn${i === 0 ? " active" : ""}" onclick="switchTab(this, 'tab-${i}')">${m}</button>`).join("\n        ")}
      </div>
      ${SUPPORTED_MODELS.map((model, i) => `
      <div id="tab-${i}" class="tab-content${i === 0 ? " active" : ""}">
        <div class="code-block">
          <div class="code-header">
            <span class="lang-tag">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
                <polyline points="13 2 13 9 20 9"/>
              </svg>
              Python · requests
            </span>
            <button class="copy-btn" onclick="copyCode(this)">Copy</button>
          </div>
          <pre>import requests

url = "https://your-domain.com/api/v2/chat/ai"

payload = {
    "model": "${model}",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"}
    ],
    "temperature": 0.7,
    "max_tokens": 2048,
    "stream": False
}

headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_API_KEY"
}

response = requests.post(url, json=payload, headers=headers)
data = response.json()

print("Model:", data["model"])
print("Reply:", data["choices"][0]["message"]["content"])
print("Tokens used:", data["usage"]["total_tokens"])</pre>
        </div>
      </div>`).join("\n      ")}
    </section>

    <section id="section-response">
      <h2>Response Format</h2>
      <div class="code-block">
        <div class="code-header">
          <span class="lang-tag">JSON</span>
          <button class="copy-btn" onclick="copyCode(this)">Copy</button>
        </div>
        <pre>{
  "id": "chatcmpl-1716134400000",
  "object": "chat.completion",
  "created": 1716134400,
  "model": "gpt-4o",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! I'm doing great. How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 28,
    "completion_tokens": 14,
    "total_tokens": 42
  },
  "meta": {
    "temperature": 0.7,
    "max_tokens": 2048
  }
}</pre>
      </div>
    </section>

    <div id="no-results">No results found for your search.</div>
  </main>

  <script>
    function switchTab(btn, tabId) {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(tabId).classList.add("active");
    }

    function copyCode(btn) {
      const pre = btn.closest(".code-block").querySelector("pre");
      navigator.clipboard.writeText(pre.textContent).then(() => {
        btn.textContent = "Copied!";
        setTimeout(() => { btn.textContent = "Copy"; }, 2000);
      });
    }

    function newChat() {
      const model = prompt("Enter model ID (e.g. gpt-4o):", "gpt-4o");
      if (!model) return;
      alert("New chat created with model: " + model + "\\n\\nIn production this would open a chat session.");
    }

    const searchInput = document.getElementById("search");
    const sections = document.querySelectorAll("section");
    const noResults = document.getElementById("no-results");

    searchInput.addEventListener("input", () => {
      const q = searchInput.value.trim().toLowerCase();
      let found = 0;

      sections.forEach(section => {
        const text = section.textContent.toLowerCase();
        if (!q || text.includes(q)) {
          section.style.display = "";
          found++;
        } else {
          section.style.display = "none";
        }
      });

      noResults.style.display = (q && found === 0) ? "block" : "none";
    });
  </script>
</body>
</html>`;

  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.send(html);
});

export default router;

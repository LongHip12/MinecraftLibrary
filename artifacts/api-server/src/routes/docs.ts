import { Router, type IRouter } from "express";

const router: IRouter = Router();

const MODELS: Record<string, { name: string; image: string; reasoning: boolean; envKey: string }> = {
  "gpt-4o-mini":      { name: "GPT-4o-mini",       image: "https://i.imgur.com/0DwnmdY.jpeg", reasoning: false, envKey: "OPENROUTER_KEY" },
  "nvidia-nemotron":  { name: "Nvidia Nemotron",    image: "https://i.imgur.com/DJgiwrh.png",  reasoning: true,  envKey: "NVIDIA_NEMOTRON_KEY" },
  "deepseek-v4-flash":{ name: "DeepSeek V4 Flash",  image: "https://i.imgur.com/0BQqhba.png",  reasoning: false, envKey: "NVIDIA_DEEPSEEK_KEY" },
  "lonely-ai":        { name: "Lonely AI",           image: "https://i.imgur.com/xY7M2iE.jpeg", reasoning: true,  envKey: "OPENROUTER_POOLSIDE_KEY" },
  "llama-3.3-70b":    { name: "Meta Llama 3.3 70B", image: "https://i.imgur.com/pESTVyY.jpeg", reasoning: false, envKey: "NVIDIA_LLAMA_KEY" },
  "gemini":           { name: "Gemini Flash",        image: "https://i.imgur.com/GdLBseU.jpeg", reasoning: false, envKey: "GOOGLE_GEMINI_KEY" },
  "kimi-k2.6":        { name: "Kimi K2.6",           image: "https://i.imgur.com/COgMkUi.jpeg", reasoning: true,  envKey: "NVIDIA_KIMI_KEY" },
};

const ENV_VARS = [
  { key: "OPENROUTER_KEY",        req: true,  desc: "OpenRouter API key — used for GPT-4o-mini" },
  { key: "OPENROUTER_POOLSIDE_KEY", req: true, desc: "OpenRouter API key — used for Lonely AI (Poolside)" },
  { key: "NVIDIA_NEMOTRON_KEY",   req: true,  desc: "NVIDIA NIM API key — used for Nvidia Nemotron" },
  { key: "NVIDIA_DEEPSEEK_KEY",   req: true,  desc: "NVIDIA NIM API key — used for DeepSeek V4 Flash" },
  { key: "NVIDIA_LLAMA_KEY",      req: true,  desc: "NVIDIA NIM API key — used for Meta Llama 3.3 70B" },
  { key: "NVIDIA_KIMI_KEY",       req: true,  desc: "NVIDIA NIM API key — used for Kimi K2.6" },
  { key: "GOOGLE_GEMINI_KEY",     req: true,  desc: "Google AI Studio API key — used for Gemini Flash" },
  { key: "DATABASE_URL",          req: true,  desc: "PostgreSQL connection string for Drizzle ORM" },
  { key: "SESSION_SECRET",        req: true,  desc: "Secret for signing session cookies (32+ chars)" },
  { key: "PORT",                  req: false, desc: "Express server port. Defaults to 5000 in dev" },
  { key: "NODE_ENV",              req: false, desc: "Set to production in deployed environments" },
];

router.get("/docs", (_req, res) => {
  const modelsJson = JSON.stringify(MODELS);

  const modelItemsHtml = Object.entries(MODELS).map(([key, m]) => `
    <div class="ai-model-item${key === "gpt-4o-mini" ? " active" : ""}" data-key="${key}" onclick="selectModel('${key}')">
      <img src="${m.image}" alt="${m.name}">
      <div class="ai-model-item-info">
        <div class="ai-model-item-name">${m.name}</div>
        <div class="ai-model-item-tag${m.reasoning ? " reasoning" : ""}">
          ${m.reasoning
            ? `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="2.2"/><ellipse cx="12" cy="12" rx="10" ry="4"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-60 12 12)"/></svg>Supports reasoning`
            : "Standard"}
        </div>
      </div>
      <svg class="ai-model-item-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
    </div>`).join("");

  const envHtml = ENV_VARS.map(e => `
    <div class="env-item">
      <div class="env-dot ${e.req ? "req" : "opt"}"></div>
      <code class="env-key">${e.key}</code>
      <span class="env-desc">${e.desc}</span>
    </div>`).join("");

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Lonely AI — Lonely Hub</title>
<link rel="icon" type="image/jpeg" href="https://i.imgur.com/xY7M2iE.jpeg">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
*:focus{outline:none}
button,a,input,textarea,select{-webkit-tap-highlight-color:transparent;outline:none}
button:focus-visible,a:focus-visible,input:focus-visible,textarea:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
:root{
  --bg:#0c0e11;--bg2:#111418;--bg3:#191d24;--bg4:#20242d;--bg5:#272c36;
  --border:rgba(255,255,255,0.07);--border2:rgba(255,255,255,0.12);
  --text:#e2e5ea;--text2:#8b929e;--text3:#555d6b;
  --primary:#e05252;--primary-dim:rgba(224,82,82,0.12);--primary-border:rgba(224,82,82,0.25);
  --reasoning:#a78bfa;--reasoning-dim:rgba(167,139,250,0.1);
  --radius:14px;--sb:260px;--topbar:52px;
}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;font-size:14px;-webkit-font-smoothing:antialiased}
button{cursor:pointer;background:none;border:none;color:inherit;font-family:inherit;font-size:inherit;-webkit-appearance:none}
a{color:inherit;text-decoration:none}
textarea{font-family:inherit;font-size:inherit;color:inherit;-webkit-appearance:none}
input{font-family:inherit;color:inherit;-webkit-appearance:none}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--bg5);border-radius:6px}

/* ── Top nav bar ────────────────── */
.site-nav{
  position:fixed;top:0;left:0;right:0;z-index:200;
  height:52px;background:rgba(12,14,17,.9);backdrop-filter:blur(12px);
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;padding:0 20px;gap:4px;
}
.site-nav-logo{display:flex;align-items:center;gap:9px;font-weight:700;font-size:15px;margin-right:12px;flex-shrink:0}
.site-nav-logo img{width:28px;height:28px;border-radius:7px;object-fit:cover}
.site-nav-link{
  display:flex;align-items:center;gap:6px;padding:6px 12px;border-radius:9px;
  font-size:13px;font-weight:500;color:var(--text2);transition:background .13s,color .13s;flex-shrink:0;
}
.site-nav-link:hover{background:var(--bg3);color:var(--text)}
.site-nav-link.active{color:var(--primary)}
.site-nav-link svg{flex-shrink:0;opacity:.7}
.site-nav-gap{flex:1}
@media(max-width:600px){
  .site-nav-link span{display:none}
  .site-nav-link{padding:6px 9px}
}

/* ── Chat layout ────────────────── */
.ai-layout{display:flex;height:100vh;padding-top:52px;overflow:hidden;position:relative}

/* ── Sidebar ────────────────── */
.ai-sb{
  width:var(--sb);flex-shrink:0;background:var(--bg2);
  border-right:1px solid var(--border);
  display:flex;flex-direction:column;overflow:hidden;
  transition:transform .22s cubic-bezier(.4,0,.2,1);
  z-index:50;
}
.ai-sb-head{padding:12px 10px 10px;display:flex;flex-direction:column;gap:8px;flex-shrink:0;border-bottom:1px solid var(--border)}
.ai-sb-new{
  display:flex;align-items:center;gap:8px;width:100%;padding:9px 12px;
  background:var(--primary-dim);border:1px solid var(--primary-border);
  border-radius:10px;color:var(--primary);font-size:13px;font-weight:600;
  transition:background .13s,border-color .13s;
}
.ai-sb-new:hover{background:rgba(224,82,82,0.18);border-color:var(--primary)}
.ai-sb-search-wrap{position:relative}
.ai-sb-search-wrap svg{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--text3);pointer-events:none}
.ai-sb-search{
  width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:9px;
  padding:7px 10px 7px 32px;font-size:13px;color:var(--text);transition:border-color .15s;
}
.ai-sb-search::placeholder{color:var(--text3)}
.ai-sb-search:focus{border-color:var(--border2)}
.ai-sb-list{flex:1;overflow-y:auto;padding:6px}
.ai-sb-section{font-size:10.5px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.6px;padding:8px 8px 4px}
.ai-chat-item{
  display:flex;align-items:center;gap:7px;padding:8px 10px;border-radius:10px;
  cursor:pointer;color:var(--text2);font-size:13px;position:relative;
  margin:1px 0;transition:background .13s,color .13s;user-select:none;
}
.ai-chat-item:hover{background:var(--bg3);color:var(--text)}
.ai-chat-item.active{background:var(--bg4);color:var(--text)}
.ai-chat-pin{width:7px;height:7px;background:var(--primary);border-radius:50%;flex-shrink:0}
.ai-chat-title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}
.ai-chat-del{
  opacity:0;width:22px;height:22px;border-radius:6px;display:flex;align-items:center;justify-content:center;
  color:var(--text3);transition:background .12s,color .12s,opacity .12s;flex-shrink:0;
}
.ai-chat-item:hover .ai-chat-del{opacity:1}
.ai-chat-del:hover{background:rgba(248,113,113,.12);color:#f87171}
.ai-sb-empty{padding:24px 12px;text-align:center;color:var(--text3);font-size:13px}

/* ── Overlay (mobile sidebar) ────── */
.ai-overlay{display:none;position:fixed;inset:0;top:52px;background:rgba(0,0,0,.55);z-index:49;backdrop-filter:blur(2px)}
.ai-overlay.on{display:block}

/* ── Mobile sidebar ────────────── */
@media(max-width:768px){
  .ai-sb{
    position:fixed;left:0;top:52px;bottom:0;
    transform:translateX(-100%);
    box-shadow:4px 0 24px rgba(0,0,0,.5);
  }
  .ai-sb.open{transform:translateX(0)}
  .ai-topbar-toggle{display:flex!important}
}

/* ── Main area ────────────────────── */
.ai-main{flex:1;display:flex;flex-direction:column;min-width:0;overflow:hidden;background:var(--bg)}

/* ── Topbar ────────────────────── */
.ai-topbar{
  height:var(--topbar);display:flex;align-items:center;padding:0 10px;gap:6px;
  border-bottom:1px solid var(--border);flex-shrink:0;
}
.ai-icon-btn{
  width:34px;height:34px;border-radius:8px;display:flex;align-items:center;
  justify-content:center;color:var(--text2);transition:background .13s,color .13s;flex-shrink:0;
}
.ai-icon-btn:hover{background:var(--bg3);color:var(--text)}
.ai-topbar-toggle{display:none}
.ai-topbar-title{font-size:14px;font-weight:600;color:var(--text2);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ai-topbar-right{display:flex;align-items:center;gap:6px;margin-left:auto}

/* ── Model selector ────────────── */
.ai-model-sel{position:relative}
.ai-model-btn{
  display:flex;align-items:center;gap:7px;padding:6px 10px 6px 8px;
  background:var(--bg3);border:1px solid var(--border);border-radius:20px;
  cursor:pointer;color:var(--text);font-size:13px;font-weight:500;
  transition:background .13s,border-color .13s;
}
.ai-model-btn:hover{background:var(--bg4);border-color:var(--border2)}
.ai-model-btn img{width:20px;height:20px;border-radius:50%;object-fit:cover;flex-shrink:0}
.ai-model-chevron{opacity:.5;transition:transform .2s;flex-shrink:0}
.ai-model-chevron.open{transform:rotate(180deg)}
.ai-model-dd{
  position:absolute;top:calc(100% + 6px);right:0;
  background:var(--bg3);border:1px solid var(--border2);border-radius:14px;
  padding:6px;min-width:230px;z-index:300;
  box-shadow:0 16px 48px rgba(0,0,0,.6);display:none;
}
.ai-model-dd.open{display:block}
.ai-model-item{
  display:flex;align-items:center;gap:10px;padding:9px 10px;
  border-radius:9px;cursor:pointer;transition:background .12s;
}
.ai-model-item:hover{background:var(--bg4)}
.ai-model-item.active{background:var(--primary-dim)}
.ai-model-item img{width:30px;height:30px;border-radius:50%;object-fit:cover;flex-shrink:0}
.ai-model-item-info{flex:1;min-width:0}
.ai-model-item-name{font-size:13px;font-weight:500;color:var(--text)}
.ai-model-item-tag{font-size:11px;color:var(--text3);display:flex;align-items:center;gap:4px;margin-top:1px}
.ai-model-item-tag.reasoning{color:var(--reasoning)}
.ai-model-item-check{color:var(--primary);opacity:0;flex-shrink:0}
.ai-model-item.active .ai-model-item-check{opacity:1}

/* ── Reasoning toggle btn ────────── */
.ai-reasoning-btn{
  display:none;align-items:center;gap:6px;padding:5px 12px;
  background:var(--bg3);border:1px solid var(--border);border-radius:20px;
  font-size:12px;font-weight:500;color:var(--text2);
  transition:background .13s,border-color .13s,color .13s;
}
.ai-reasoning-btn:hover{background:var(--bg4);border-color:var(--border2)}
.ai-reasoning-btn.active{background:var(--reasoning-dim);border-color:rgba(167,139,250,.3);color:var(--reasoning)}

/* ── Messages area ────────────── */
.ai-msgs{flex:1;min-height:0;overflow-y:auto;padding:20px 16px 8px}
.ai-msgs-inner{display:flex;flex-direction:column;gap:18px;max-width:760px;width:100%;margin:0 auto}

/* ── Welcome ────────────────────── */
.ai-welcome{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px;min-height:calc(100svh - 52px - 52px - 100px)}
.ai-welcome-icon{width:72px;height:72px;border-radius:20px;background:var(--primary-dim);border:1px solid var(--primary-border);display:flex;align-items:center;justify-content:center;margin-bottom:20px;flex-shrink:0}
.ai-welcome-title{font-size:26px;font-weight:800;margin-bottom:6px;text-align:center}
.ai-welcome-sub{font-size:14px;color:var(--text2);margin-bottom:32px;text-align:center}
.ai-suggestions{display:grid;grid-template-columns:1fr 1fr;gap:10px;max-width:500px;width:100%}
.ai-sug-card{
  background:var(--bg3);border:1px solid var(--border);border-radius:14px;
  padding:16px;cursor:pointer;text-align:left;
  transition:background .15s,border-color .15s,transform .12s;
}
.ai-sug-card:hover{background:var(--bg4);border-color:var(--border2);transform:translateY(-1px)}
.ai-sug-card svg{display:block;margin-bottom:10px;opacity:.8;color:var(--text2)}
.ai-sug-card-text{font-size:13px;color:var(--text);line-height:1.5}
@media(max-width:480px){.ai-suggestions{grid-template-columns:1fr}}

/* ── Message bubbles ────────────── */
.ai-msg{display:flex;gap:10px;max-width:760px;width:100%;margin:0 auto;position:relative}
.ai-msg.user{flex-direction:row-reverse;align-self:flex-end}
.ai-msg.assistant{align-self:flex-start}
.ai-msg-avatar{width:28px;height:28px;border-radius:50%;object-fit:cover;flex-shrink:0;margin-top:2px}
.ai-msg-body{display:flex;flex-direction:column;gap:4px;min-width:0;max-width:680px}
.ai-msg.user .ai-msg-body{align-items:flex-end}
.ai-msg-meta{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--text3);padding:0 4px}
.ai-msg.user .ai-msg-meta{flex-direction:row-reverse}
.ai-msg-meta img{width:16px;height:16px;border-radius:50%;object-fit:cover}
.ai-msg-bubble{padding:12px 16px;border-radius:16px;font-size:14px;line-height:1.7;word-break:break-word}
.ai-msg.user .ai-msg-bubble{background:var(--primary-dim);border:1px solid var(--primary-border);border-radius:18px 4px 18px 18px;color:var(--text)}
.ai-msg.assistant .ai-msg-bubble{background:var(--bg3);border:1px solid var(--border);border-radius:4px 18px 18px 18px;color:var(--text)}

/* ── Reasoning block ────────────── */
.ai-reasoning-block{background:var(--reasoning-dim);border:1px solid rgba(167,139,250,.2);border-radius:12px;margin-bottom:6px;overflow:hidden}
.ai-reasoning-hd{display:flex;align-items:center;gap:7px;padding:9px 13px;cursor:pointer;font-size:13px;color:var(--reasoning);user-select:none}
.ai-reasoning-hd svg{flex-shrink:0}
.ai-reasoning-chev{transition:transform .2s;margin-left:auto;opacity:.6}
.ai-reasoning-hd.open .ai-reasoning-chev{transform:rotate(90deg)}
.ai-reasoning-bd{display:none;padding:10px 14px 13px;font-size:12.5px;color:var(--text2);line-height:1.7;border-top:1px solid rgba(167,139,250,.15);white-space:pre-wrap;word-break:break-word}
.ai-reasoning-bd.open{display:block}

/* ── Loading dots ────────────────── */
@keyframes _aidot{0%,60%,100%{transform:translateY(0);opacity:.3}30%{transform:translateY(-5px);opacity:1}}
.ai-dots{display:flex;align-items:center;gap:4px;padding:14px 16px}
.ai-dots span{width:7px;height:7px;background:var(--text3);border-radius:50%;animation:_aidot 1.2s infinite}
.ai-dots span:nth-child(2){animation-delay:.15s}
.ai-dots span:nth-child(3){animation-delay:.3s}

/* ── Message actions ────────────── */
.ai-msg-actions{display:flex;align-items:center;gap:2px;margin-top:4px;padding:0 2px;opacity:0;transition:opacity .15s}
.ai-msg:hover .ai-msg-actions{opacity:1}
.ai-msg-action-btn{width:28px;height:28px;border-radius:7px;display:flex;align-items:center;justify-content:center;color:var(--text3);transition:background .12s,color .12s}
.ai-msg-action-btn:hover{background:var(--bg4);color:var(--text2)}

/* ── Code blocks ────────────────── */
.ai-code-wrap{background:#13151a;border:1px solid rgba(255,255,255,.09);border-radius:12px;margin:10px 0;overflow:hidden}
.ai-code-hd{display:flex;align-items:center;justify-content:space-between;padding:8px 14px;background:#1a1d24;border-bottom:1px solid rgba(255,255,255,.07)}
.ai-code-lang{font-size:11px;font-weight:600;color:#8b929e;text-transform:uppercase;letter-spacing:.6px}
.ai-code-copy{display:flex;align-items:center;gap:5px;font-size:11px;color:#8b929e;padding:3px 8px;border-radius:6px;transition:background .12s,color .12s}
.ai-code-copy:hover{background:rgba(255,255,255,.07);color:#c9d1d9}
.ai-code-body{overflow-x:auto}
.ai-code-body pre{margin:0}
.ai-code-body code.hljs{background:transparent;padding:14px 16px;font-size:13px;line-height:1.6}

/* ── Input section ────────────────── */
.ai-input-section{
  flex-shrink:0;
  padding:8px 16px max(14px, env(safe-area-inset-bottom));
  border-top:1px solid var(--border);
  background:var(--bg);
  position:relative;
  z-index:10;
}
.ai-input-bar{
  display:flex;align-items:flex-end;gap:6px;
  background:var(--bg3);border:1px solid var(--border);border-radius:16px;
  padding:10px 10px 10px 16px;max-width:760px;margin:0 auto;
  transition:border-color .15s;
}
.ai-input-bar:focus-within{border-color:var(--border2)}
.ai-ta{
  flex:1;background:none;border:none;resize:none;
  font-size:14px;line-height:1.6;color:var(--text);
  max-height:180px;overflow-y:auto;
  scrollbar-width:none;
}
.ai-ta::-webkit-scrollbar{display:none}
.ai-ta::placeholder{color:var(--text3)}
.ai-send-btn{
  width:34px;height:34px;border-radius:10px;flex-shrink:0;
  display:flex;align-items:center;justify-content:center;
  background:var(--primary);color:#fff;
  transition:background .13s,transform .1s,opacity .13s;
}
.ai-send-btn:hover{background:#cc4444;transform:translateY(-1px)}
.ai-send-btn:active{transform:translateY(0)}
.ai-send-btn:disabled{opacity:.4;transform:none;cursor:not-allowed}
.ai-input-hint{text-align:center;font-size:11.5px;color:var(--text3);margin-top:8px;max-width:760px;margin-left:auto;margin-right:auto}

/* ── API Docs panel ────────────────── */
.ai-docs-overlay{display:none;position:fixed;inset:0;top:52px;background:rgba(0,0,0,.7);z-index:400;backdrop-filter:blur(4px);align-items:flex-end;justify-content:center}
.ai-docs-overlay.on{display:flex}
.ai-docs-panel{
  background:var(--bg2);border:1px solid var(--border2);border-radius:20px 20px 0 0;
  width:100%;max-width:820px;max-height:85vh;display:flex;flex-direction:column;
  box-shadow:0 -16px 48px rgba(0,0,0,.6);
}
.ai-docs-head{display:flex;align-items:center;justify-content:space-between;padding:18px 22px 14px;border-bottom:1px solid var(--border);flex-shrink:0}
.ai-docs-head-title{font-size:16px;font-weight:700}
.ai-docs-close{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--text2);transition:background .13s}
.ai-docs-close:hover{background:var(--bg3)}
.ai-docs-body{overflow-y:auto;padding:20px 22px 28px;display:flex;flex-direction:column;gap:20px}
.ai-docs-section-title{font-size:13px;font-weight:700;color:var(--text2);letter-spacing:.4px;text-transform:uppercase;margin-bottom:10px}
.ai-docs-model-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}
.ai-docs-model-card{background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:12px 14px;display:flex;align-items:center;gap:10px}
.ai-docs-model-card img{width:28px;height:28px;border-radius:50%;object-fit:cover;flex-shrink:0}
.ai-docs-model-card-info{flex:1;min-width:0}
.ai-docs-model-card-name{font-size:13px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ai-docs-model-card-key{font-size:11px;color:var(--text3);font-family:monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px}
.env-list{display:flex;flex-direction:column;gap:6px}
.env-item{display:flex;align-items:center;gap:10px;background:var(--bg3);border:1px solid var(--border);border-radius:9px;padding:10px 14px}
.env-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.env-dot.req{background:#f87171}
.env-dot.opt{background:var(--text3)}
.env-key{font-family:monospace;font-size:12px;color:#34d399;min-width:220px;white-space:nowrap}
.env-desc{font-size:12px;color:var(--text2)}
@media(max-width:600px){.env-item{flex-wrap:wrap;gap:6px}.env-key{min-width:unset}}

/* ── Python code tab ────────────── */
.py-tabs{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:12px;border-bottom:1px solid var(--border);padding-bottom:0}
.py-tab{background:none;border:none;border-bottom:2px solid transparent;margin-bottom:-1px;padding:7px 14px;font-size:12.5px;font-weight:600;color:var(--text3);cursor:pointer;transition:color .13s,border-color .13s}
.py-tab.active{color:var(--primary);border-bottom-color:var(--primary)}
.py-tab-content{display:none}
.py-tab-content.active{display:block}
.py-code-block{background:#0d0f16;border:1px solid var(--border);border-radius:12px;overflow:hidden}
.py-code-hd{display:flex;align-items:center;justify-content:space-between;padding:9px 14px;background:var(--bg3);border-bottom:1px solid var(--border);font-size:12px}
.py-code-lang{font-weight:700;color:#f59e0b}
.py-copy-btn{background:none;border:1px solid var(--border);color:var(--text3);font-size:11px;padding:3px 10px;border-radius:6px;cursor:pointer;transition:border-color .13s,color .13s}
.py-copy-btn:hover{border-color:var(--primary);color:var(--primary)}
.py-code-block pre{margin:0;padding:16px;overflow-x:auto;font-family:monospace;font-size:12.5px;line-height:1.7;color:#c8d3f5;tab-size:4}
</style>
</head>
<body>
<!-- ── Top nav ────────────────────── -->
<nav class="site-nav">
  <a href="/" class="site-nav-logo">
    <img src="https://i.imgur.com/xY7M2iE.jpeg" alt="Lonely Hub">
    <span>Lonely Hub</span>
  </a>
  <a href="/" class="site-nav-link"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg><span>Home</span></a>
  <a href="/mods" class="site-nav-link"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg><span>Mods</span></a>
  <a href="/clients" class="site-nav-link"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><polyline points="8 21 12 17 16 21"/><line x1="6" y1="8" x2="18" y2="8"/><line x1="6" y1="12" x2="14" y2="12"/></svg><span>Clients</span></a>
  <a href="/forum" class="site-nav-link"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg><span>Forum</span></a>
  <a href="/api/docs" class="site-nav-link active"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="2"/><ellipse cx="12" cy="12" rx="10" ry="4"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-60 12 12)"/></svg><span>AI Chat</span></a>
  <div class="site-nav-gap"></div>
  <button class="ai-icon-btn" onclick="openDocs()" title="API Docs" style="flex-shrink:0">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
  </button>
</nav>

<!-- ── Chat layout ────────────────── -->
<div class="ai-layout">
  <!-- Sidebar overlay (mobile) -->
  <div class="ai-overlay" id="ai-overlay" onclick="closeSidebar()"></div>

  <!-- Sidebar -->
  <div class="ai-sb" id="ai-sb">
    <div class="ai-sb-head">
      <button class="ai-sb-new" onclick="newChat()">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12h14"/></svg>
        Create a new chat
      </button>
      <div class="ai-sb-search-wrap">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
        <input class="ai-sb-search" id="ai-sb-search" type="text" placeholder="Search chats..." oninput="filterChats()" autocomplete="off">
      </div>
    </div>
    <div class="ai-sb-list" id="ai-sb-list"></div>
  </div>

  <!-- Main -->
  <div class="ai-main">
    <!-- Topbar -->
    <div class="ai-topbar">
      <button class="ai-icon-btn ai-topbar-toggle" id="ai-topbar-toggle" onclick="toggleSidebar()">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      </button>
      <div class="ai-topbar-title" id="ai-topbar-title">Lonely AI</div>
      <div class="ai-topbar-right">
        <button class="ai-reasoning-btn" id="ai-reasoning-btn" onclick="toggleReasoning()">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="2"/><ellipse cx="12" cy="12" rx="10" ry="4"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-60 12 12)"/></svg>
          Reasoning
        </button>
        <div class="ai-model-sel">
          <button class="ai-model-btn" id="ai-model-btn" onclick="toggleModelDD(event)">
            <img id="ai-model-img" src="https://i.imgur.com/0DwnmdY.jpeg" alt="">
            <span id="ai-model-name">GPT-4o-mini</span>
            <svg class="ai-model-chevron" id="ai-model-chev" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <div class="ai-model-dd" id="ai-model-dd">${modelItemsHtml}</div>
        </div>
      </div>
    </div>

    <!-- Messages -->
    <div class="ai-msgs" id="ai-msgs">
      <div class="ai-msgs-inner" id="ai-msgs-inner"></div>
    </div>

    <!-- Input -->
    <div class="ai-input-section">
      <div class="ai-input-bar">
        <textarea class="ai-ta" id="ai-ta" rows="1" placeholder="Message Lonely AI…" onkeydown="handleKey(event)" oninput="autoGrow()"></textarea>
        <button class="ai-send-btn" id="ai-send-btn" onclick="sendMsg()" disabled>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </div>
      <div class="ai-input-hint">Lonely AI can make mistakes. Check important info.</div>
    </div>
  </div>
</div>

<!-- ── API Docs panel ────────────────── -->
<div class="ai-docs-overlay" id="ai-docs-overlay" onclick="closeDocs(event)">
  <div class="ai-docs-panel" onclick="event.stopPropagation()">
    <div class="ai-docs-head">
      <span class="ai-docs-head-title">API Reference — /api/v2/chat/ai</span>
      <button class="ai-docs-close" onclick="closeDocs()">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>
    <div class="ai-docs-body">
      <div>
        <div class="ai-docs-section-title">Supported Models (7)</div>
        <div class="ai-docs-model-grid">
          ${Object.entries(MODELS).map(([key, m]) => `
          <div class="ai-docs-model-card">
            <img src="${m.image}" alt="${m.name}">
            <div class="ai-docs-model-card-info">
              <div class="ai-docs-model-card-name">${m.name}</div>
              <div class="ai-docs-model-card-key">${key}</div>
            </div>
          </div>`).join("")}
        </div>
      </div>
      <div>
        <div class="ai-docs-section-title">Python Examples</div>
        <div class="py-tabs">
          ${Object.keys(MODELS).map((key, i) => `<button class="py-tab${i === 0 ? " active" : ""}" onclick="switchPyTab(this,'py-${i}')">${MODELS[key].name}</button>`).join("")}
        </div>
        ${Object.entries(MODELS).map(([key, m], i) => `
        <div id="py-${i}" class="py-tab-content${i === 0 ? " active" : ""}">
          <div class="py-code-block">
            <div class="py-code-hd">
              <span class="py-code-lang">Python</span>
              <button class="py-copy-btn" onclick="copyPy(this)">Copy</button>
            </div>
            <pre>import requests

response = requests.post(
    "https://your-domain.com/api/v2/chat/ai",
    headers={"Content-Type": "application/json"},
    json={
        "model": "${key}",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"}
        ],
        "temperature": 0.7,
        "max_tokens": 2048,${m.reasoning ? `
        "reasoning": True,` : ""}
    }
)
print(response.json()["choices"][0]["message"]["content"])</pre>
          </div>
        </div>`).join("")}
      </div>
      <div>
        <div class="ai-docs-section-title">Environment Variables</div>
        <div class="env-list">${envHtml}</div>
      </div>
    </div>
  </div>
</div>

<script>
var MODELS = ${modelsJson};
var S = {
  model: 'gpt-4o-mini',
  chatId: null,
  reasoning: false,
  sending: false,
  sbOpen: window.innerWidth > 768,
};

var _renderer = new marked.Renderer();
_renderer.code = function(code, lang) {
  var language = (lang || 'text').toLowerCase();
  var highlighted;
  try {
    if (hljs.getLanguage(language)) {
      highlighted = hljs.highlight(code, { language: language }).value;
    } else {
      highlighted = hljs.highlightAuto(code).value;
    }
  } catch(e) {
    highlighted = hljs.highlightAuto(code).value;
  }
  return '<div class="ai-code-wrap">' +
    '<div class="ai-code-hd">' +
      '<span class="ai-code-lang">' + (lang || 'code') + '</span>' +
      '<button class="ai-code-copy" onclick="copyCodeBlock(this)">' +
        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>Copy' +
      '</button>' +
    '</div>' +
    '<div class="ai-code-body"><pre><code class="hljs">' + highlighted + '</code></pre></div>' +
  '</div>';
};
marked.use({ renderer: _renderer, breaks: true, gfm: true });

function copyCodeBlock(btn) {
  var code = btn.closest('.ai-code-wrap').querySelector('code').innerText;
  navigator.clipboard.writeText(code).then(function() {
    btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>Copied';
    setTimeout(function() {
      btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>Copy';
    }, 1500);
  });
}

function getChats() {
  try { return JSON.parse(localStorage.getItem('ai_chats') || '[]'); } catch(e) { return []; }
}
function saveChats(chats) {
  localStorage.setItem('ai_chats', JSON.stringify(chats));
}
function getChat(id) {
  return getChats().find(function(c) { return c.id === id; }) || null;
}
function upsertChat(chat) {
  var chats = getChats();
  var idx = chats.findIndex(function(c) { return c.id === chat.id; });
  if (idx >= 0) { chats[idx] = chat; } else { chats.unshift(chat); }
  saveChats(chats);
}

function renderSidebar(filter) {
  var chats = getChats();
  var list = document.getElementById('ai-sb-list');
  filter = (filter || '').toLowerCase().trim();
  if (filter) { chats = chats.filter(function(c) { return c.title.toLowerCase().includes(filter); }); }
  if (!chats.length) {
    list.innerHTML = '<div class="ai-sb-empty">' + (filter ? 'No results.' : 'No chats yet.') + '</div>';
    return;
  }
  var pinned = chats.filter(function(c) { return c.pinned; });
  var recent = chats.filter(function(c) { return !c.pinned; });
  var html = '';
  if (pinned.length) {
    html += '<div class="ai-sb-section">Pinned</div>';
    pinned.forEach(function(c) { html += chatItemHtml(c); });
  }
  if (recent.length) {
    if (pinned.length) html += '<div class="ai-sb-section">Recent</div>';
    recent.forEach(function(c) { html += chatItemHtml(c); });
  }
  list.innerHTML = html;
}

function chatItemHtml(c) {
  return '<div class="ai-chat-item' + (c.id === S.chatId ? ' active' : '') + '" data-id="' + c.id + '" onclick="openChat(\'' + c.id + '\')">' +
    (c.pinned ? '<div class="ai-chat-pin"></div>' : '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:.35;flex-shrink:0"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>') +
    '<span class="ai-chat-title">' + escHtml(c.title) + '</span>' +
    '<button class="ai-chat-del" onclick="deleteChat(event,\'' + c.id + '\')" title="Delete">' +
      '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>' +
    '</button>' +
  '</div>';
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function filterChats() {
  renderSidebar(document.getElementById('ai-sb-search').value);
}

function openChat(id) {
  if (S.sending) return;
  S.chatId = id;
  var chat = getChat(id);
  if (!chat) return;
  document.getElementById('ai-topbar-title').textContent = chat.title;
  if (chat.model && MODELS[chat.model]) { setModel(chat.model); }
  renderMessages(chat.messages || []);
  renderSidebar(document.getElementById('ai-sb-search').value);
  if (window.innerWidth <= 768) { closeSidebar(); }
}

function newChat() {
  if (S.sending) return;
  S.chatId = null;
  document.getElementById('ai-topbar-title').textContent = 'Lonely AI';
  renderSidebar(document.getElementById('ai-sb-search').value);
  showWelcome();
  if (window.innerWidth <= 768) { closeSidebar(); }
}

function deleteChat(e, id) {
  e.stopPropagation();
  var chats = getChats().filter(function(c) { return c.id !== id; });
  saveChats(chats);
  if (S.chatId === id) {
    S.chatId = null;
    document.getElementById('ai-topbar-title').textContent = 'Lonely AI';
    showWelcome();
  }
  renderSidebar(document.getElementById('ai-sb-search').value);
}

function toggleSidebar() {
  var sb = document.getElementById('ai-sb');
  var ov = document.getElementById('ai-overlay');
  if (window.innerWidth <= 768) {
    S.sbOpen = !S.sbOpen;
    sb.classList.toggle('open', S.sbOpen);
    ov.classList.toggle('on', S.sbOpen);
  } else {
    S.sbOpen = !S.sbOpen;
    sb.style.display = S.sbOpen ? '' : 'none';
  }
}
function closeSidebar() {
  S.sbOpen = false;
  document.getElementById('ai-sb').classList.remove('open');
  document.getElementById('ai-overlay').classList.remove('on');
}

function setModel(key) {
  var m = MODELS[key];
  if (!m) return;
  S.model = key;
  document.getElementById('ai-model-img').src = m.image;
  document.getElementById('ai-model-name').textContent = m.name;
  var rb = document.getElementById('ai-reasoning-btn');
  rb.style.display = m.reasoning ? 'flex' : 'none';
  if (!m.reasoning) { S.reasoning = false; rb.classList.remove('active'); }
  document.querySelectorAll('.ai-model-item').forEach(function(el) {
    el.classList.toggle('active', el.dataset.key === key);
  });
}
function selectModel(key) {
  setModel(key);
  closeModelDD();
}
function toggleModelDD(e) {
  e.stopPropagation();
  var dd = document.getElementById('ai-model-dd');
  var chev = document.getElementById('ai-model-chev');
  var open = dd.classList.toggle('open');
  chev.classList.toggle('open', open);
}
function closeModelDD() {
  document.getElementById('ai-model-dd').classList.remove('open');
  document.getElementById('ai-model-chev').classList.remove('open');
}
function toggleReasoning() {
  if (!MODELS[S.model] || !MODELS[S.model].reasoning) return;
  S.reasoning = !S.reasoning;
  document.getElementById('ai-reasoning-btn').classList.toggle('active', S.reasoning);
}

function autoGrow() {
  var ta = document.getElementById('ai-ta');
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 180) + 'px';
  document.getElementById('ai-send-btn').disabled = !ta.value.trim();
}
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!document.getElementById('ai-send-btn').disabled) sendMsg();
  }
}

function showWelcome() {
  var inner = document.getElementById('ai-msgs-inner');
  inner.innerHTML =
    '<div class="ai-welcome">' +
      '<div class="ai-welcome-icon">' +
        '<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#e05252" stroke-width="1.6"><circle cx="12" cy="12" r="2.2"/><ellipse cx="12" cy="12" rx="10" ry="4"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-60 12 12)"/></svg>' +
      '</div>' +
      '<div class="ai-welcome-title">Lonely AI</div>' +
      '<div class="ai-welcome-sub">Smart assistant — ask anything about Minecraft or coding</div>' +
      '<div class="ai-suggestions">' +
        sugCard('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>', 'Create a Minecraft mod in Java', 'Create a Minecraft mod in Java') +
        sugCard('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>', 'How to set up a Minecraft server', 'How to set up a Minecraft server') +
        sugCard('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>', 'Best Minecraft seeds in 2025', 'Best Minecraft seeds in 2025') +
        sugCard('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>', 'Fix common Minecraft Forge errors', 'Fix common Minecraft Forge errors') +
      '</div>' +
    '</div>';
}
function sugCard(icon, label, prompt) {
  return '<button class="ai-sug-card" onclick="useSuggestion(\'' + prompt.replace(/'/g,"\\'") + '\')">' + icon + '<div class="ai-sug-card-text">' + label + '</div></button>';
}
function useSuggestion(text) {
  document.getElementById('ai-ta').value = text;
  autoGrow();
  sendMsg();
}

function renderMessages(msgs) {
  var inner = document.getElementById('ai-msgs-inner');
  if (!msgs || !msgs.length) { showWelcome(); return; }
  inner.innerHTML = '';
  msgs.forEach(function(m) { inner.appendChild(buildMsgEl(m.role, m.content, m.model)); });
  scrollBottom();
}

function buildMsgEl(role, content, modelKey) {
  var div = document.createElement('div');
  div.className = 'ai-msg ' + role;
  var m = MODELS[modelKey || S.model] || MODELS['gpt-4o-mini'];
  var avatarSrc = role === 'user' ? 'https://i.imgur.com/nkwxFf4.png' : m.image;
  var name = role === 'user' ? 'You' : m.name;
  var bodyHtml = '';
  if (role === 'assistant') {
    var parsed = parseReasoningContent(content);
    if (parsed.reasoning) {
      bodyHtml += '<div class="ai-reasoning-block">' +
        '<div class="ai-reasoning-hd" onclick="toggleReasoningBlock(this)">' +
          '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="2"/><ellipse cx="12" cy="12" rx="10" ry="4"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-60 12 12)"/></svg>' +
          'Reasoning' +
          '<svg class="ai-reasoning-chev" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>' +
        '</div>' +
        '<div class="ai-reasoning-bd">' + escHtml(parsed.reasoning) + '</div>' +
      '</div>';
      content = parsed.content;
    }
    bodyHtml += '<div class="ai-msg-bubble">' + marked.parse(content) + '</div>';
  } else {
    bodyHtml += '<div class="ai-msg-bubble">' + escHtml(content).replace(/\\n/g, '<br>') + '</div>';
  }
  div.innerHTML =
    '<img class="ai-msg-avatar" src="' + avatarSrc + '" alt="">' +
    '<div class="ai-msg-body">' +
      '<div class="ai-msg-meta"><img src="' + avatarSrc + '" alt=""><span>' + name + '</span></div>' +
      bodyHtml +
      '<div class="ai-msg-actions">' +
        '<button class="ai-msg-action-btn" onclick="copyMsg(this)" title="Copy">' +
          '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>' +
        '</button>' +
      '</div>' +
    '</div>';
  return div;
}

function parseReasoningContent(content) {
  var thinkMatch = content.match(/<think>([\\s\\S]*?)<\\/think>([\\s\\S]*)/);
  if (thinkMatch) return { reasoning: thinkMatch[1].trim(), content: thinkMatch[2].trim() };
  var reasonMatch = content.match(/<reasoning>([\\s\\S]*?)<\\/reasoning>([\\s\\S]*)/);
  if (reasonMatch) return { reasoning: reasonMatch[1].trim(), content: reasonMatch[2].trim() };
  return { reasoning: null, content: content };
}

function toggleReasoningBlock(hd) {
  hd.classList.toggle('open');
  hd.nextElementSibling.classList.toggle('open');
}

function copyMsg(btn) {
  var bubble = btn.closest('.ai-msg-body').querySelector('.ai-msg-bubble');
  navigator.clipboard.writeText(bubble.innerText);
}

function scrollBottom() {
  var msgs = document.getElementById('ai-msgs');
  msgs.scrollTop = msgs.scrollHeight;
}

async function sendMsg() {
  var ta = document.getElementById('ai-ta');
  var text = ta.value.trim();
  if (!text || S.sending) return;
  S.sending = true;
  document.getElementById('ai-send-btn').disabled = true;

  var inner = document.getElementById('ai-msgs-inner');
  var welcomeEl = inner.querySelector('.ai-welcome');
  if (welcomeEl) inner.innerHTML = '';

  inner.appendChild(buildMsgEl('user', text));

  ta.value = '';
  ta.style.height = 'auto';
  document.getElementById('ai-send-btn').disabled = true;

  if (!S.chatId) {
    S.chatId = 'chat_' + Date.now();
    var title = text.length > 40 ? text.slice(0, 40) + '…' : text;
    upsertChat({ id: S.chatId, title: title, pinned: false, model: S.model, messages: [], updatedAt: Date.now() });
    document.getElementById('ai-topbar-title').textContent = title;
    renderSidebar(document.getElementById('ai-sb-search').value);
  }

  var chat = getChat(S.chatId);
  if (!chat) chat = { id: S.chatId, title: text.slice(0,40), pinned: false, model: S.model, messages: [], updatedAt: Date.now() };
  chat.messages = chat.messages || [];
  chat.messages.push({ role: 'user', content: text, model: S.model });

  var dotsEl = document.createElement('div');
  dotsEl.className = 'ai-msg assistant';
  dotsEl.innerHTML = '<img class="ai-msg-avatar" src="' + (MODELS[S.model]||MODELS['gpt-4o-mini']).image + '" alt=""><div class="ai-msg-body"><div class="ai-dots"><span></span><span></span><span></span></div></div>';
  inner.appendChild(dotsEl);
  scrollBottom();

  try {
    var resp = await fetch('/api/v2/chat/ai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: S.model,
        messages: chat.messages.map(function(m) { return { role: m.role, content: m.content }; }),
        reasoning: S.reasoning,
      }),
    });
    var data = await resp.json();
    inner.removeChild(dotsEl);
    var assistantContent = '';
    if (data.choices && data.choices[0]) {
      assistantContent = data.choices[0].message.content || '';
      if (data.choices[0].message.reasoning) {
        assistantContent = '<think>' + data.choices[0].message.reasoning + '</think>' + assistantContent;
      }
    } else if (data.error) {
      assistantContent = 'Error: ' + data.error;
    }
    chat.messages.push({ role: 'assistant', content: assistantContent, model: S.model });
    chat.updatedAt = Date.now();
    upsertChat(chat);
    inner.appendChild(buildMsgEl('assistant', assistantContent, S.model));
    scrollBottom();
  } catch(e) {
    inner.removeChild(dotsEl);
    inner.appendChild(buildMsgEl('assistant', 'Network error. Please try again.', S.model));
    scrollBottom();
  }

  S.sending = false;
  document.getElementById('ai-send-btn').disabled = false;
}

function openDocs() { document.getElementById('ai-docs-overlay').classList.add('on'); }
function closeDocs(e) {
  if (!e || e.target === document.getElementById('ai-docs-overlay')) {
    document.getElementById('ai-docs-overlay').classList.remove('on');
  }
}
function switchPyTab(btn, id) {
  document.querySelectorAll('.py-tab').forEach(function(b) { b.classList.remove('active'); });
  document.querySelectorAll('.py-tab-content').forEach(function(c) { c.classList.remove('active'); });
  btn.classList.add('active');
  document.getElementById(id).classList.add('active');
}
function copyPy(btn) {
  var pre = btn.closest('.py-code-block').querySelector('pre');
  navigator.clipboard.writeText(pre.textContent).then(function() {
    btn.textContent = 'Copied!';
    setTimeout(function() { btn.textContent = 'Copy'; }, 1800);
  });
}

document.addEventListener('click', function(e) {
  if (!document.getElementById('ai-model-btn').contains(e.target)) closeModelDD();
});

document.getElementById('ai-ta').addEventListener('input', autoGrow);

window.addEventListener('resize', function() {
  var sb = document.getElementById('ai-sb');
  if (window.innerWidth > 768) {
    sb.classList.remove('open');
    document.getElementById('ai-overlay').classList.remove('on');
    sb.style.display = '';
    S.sbOpen = true;
  }
});

(function init() {
  renderSidebar();
  showWelcome();
  setModel('gpt-4o-mini');
  if (window.innerWidth <= 768) {
    S.sbOpen = false;
    document.getElementById('ai-topbar-toggle').style.display = 'flex';
  }
})();
</script>
</body>
</html>`;

  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.setHeader("Cache-Control", "no-store, no-cache, must-revalidate");
  res.setHeader("Pragma", "no-cache");
  res.setHeader("Expires", "0");
  res.send(html);
});

export default router;

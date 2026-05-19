import { Router, type IRouter, type Request, type Response } from "express";
import { z } from "zod";

const router: IRouter = Router();

const MODEL_CONFIGS: Record<string, {
  provider: "openrouter" | "nvidia" | "google";
  modelId: string;
  envKey: string;
  reasoning: boolean;
}> = {
  "gpt-4o-mini": {
    provider: "openrouter",
    modelId: "openai/gpt-4o-mini",
    envKey: "OPENROUTER_KEY",
    reasoning: false,
  },
  "nvidia-nemotron": {
    provider: "nvidia",
    modelId: "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    envKey: "NVIDIA_NEMOTRON_KEY",
    reasoning: true,
  },
  "deepseek-v4-flash": {
    provider: "nvidia",
    modelId: "deepseek-ai/deepseek-v4-flash",
    envKey: "NVIDIA_DEEPSEEK_KEY",
    reasoning: false,
  },
  "lonely-ai": {
    provider: "openrouter",
    modelId: "poolside/laguna-m.1",
    envKey: "OPENROUTER_POOLSIDE_KEY",
    reasoning: true,
  },
  "llama-3.3-70b": {
    provider: "nvidia",
    modelId: "meta/llama-3.3-70b-instruct",
    envKey: "NVIDIA_LLAMA_KEY",
    reasoning: false,
  },
  "gemini": {
    provider: "google",
    modelId: "gemini-2.0-flash",
    envKey: "GOOGLE_GEMINI_KEY",
    reasoning: false,
  },
  "kimi-k2.6": {
    provider: "nvidia",
    modelId: "moonshotai/kimi-k2.6",
    envKey: "NVIDIA_KIMI_KEY",
    reasoning: true,
  },
};

export const SUPPORTED_MODELS = Object.keys(MODEL_CONFIGS) as [string, ...string[]];

const MessageSchema = z.object({
  role: z.enum(["system", "user", "assistant"]),
  content: z.string().min(1),
});

const ChatRequestSchema = z.object({
  model: z.string(),
  messages: z.array(MessageSchema).min(1),
  temperature: z.number().min(0).max(2).optional().default(0.7),
  max_tokens: z.number().int().min(1).max(16384).optional().default(2048),
  stream: z.boolean().optional().default(false),
  reasoning: z.boolean().optional().default(false),
});

async function callOpenRouter(
  modelId: string,
  apiKey: string,
  messages: z.infer<typeof MessageSchema>[],
  temperature: number,
  maxTokens: number,
  enableReasoning: boolean,
  res: Response,
  stream: boolean,
) {
  const body: Record<string, unknown> = {
    model: modelId,
    messages,
    temperature,
    max_tokens: maxTokens,
    stream,
  };
  if (enableReasoning) {
    body["plugins"] = [{ id: "reasoner" }];
  }

  const upstream = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${apiKey}`,
      "HTTP-Referer": "https://lonelyhub.app",
      "X-Title": "Lonely Hub AI",
    },
    body: JSON.stringify(body),
  });

  if (stream) {
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    const reader = upstream.body?.getReader();
    if (!reader) { res.end(); return; }
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      res.write(decoder.decode(value, { stream: true }));
    }
    res.end();
  } else {
    const data = await upstream.json();
    res.json(data);
  }
}

async function callNvidia(
  modelId: string,
  apiKey: string,
  messages: z.infer<typeof MessageSchema>[],
  temperature: number,
  maxTokens: number,
  enableReasoning: boolean,
  res: Response,
  stream: boolean,
) {
  const body: Record<string, unknown> = {
    model: modelId,
    messages,
    temperature,
    max_tokens: maxTokens,
    stream,
  };
  if (enableReasoning) {
    body["reasoning"] = { effort: "default" };
  }

  const upstream = await fetch("https://integrate.api.nvidia.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${apiKey}`,
    },
    body: JSON.stringify(body),
  });

  if (stream) {
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    const reader = upstream.body?.getReader();
    if (!reader) { res.end(); return; }
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      res.write(decoder.decode(value, { stream: true }));
    }
    res.end();
  } else {
    const data = await upstream.json();
    res.json(data);
  }
}

async function callGoogle(
  modelId: string,
  apiKey: string,
  messages: z.infer<typeof MessageSchema>[],
  maxTokens: number,
  res: Response,
) {
  const contents = messages
    .filter((m) => m.role !== "system")
    .map((m) => ({
      role: m.role === "assistant" ? "model" : "user",
      parts: [{ text: m.content }],
    }));

  const systemMsg = messages.find((m) => m.role === "system");

  const body: Record<string, unknown> = {
    contents,
    generationConfig: { maxOutputTokens: maxTokens },
  };
  if (systemMsg) {
    body["systemInstruction"] = { parts: [{ text: systemMsg.content }] };
  }

  const upstream = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${modelId}:generateContent?key=${apiKey}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );

  const data = (await upstream.json()) as {
    candidates?: { content?: { parts?: { text?: string }[] } }[];
  };
  const text = data?.candidates?.[0]?.content?.parts?.[0]?.text ?? "";
  res.json({
    id: `chatcmpl-${Date.now()}`,
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model: modelId,
    choices: [{ index: 0, message: { role: "assistant", content: text }, finish_reason: "stop" }],
    usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
  });
}

router.post("/v2/chat/ai", async (req: Request, res: Response) => {
  const parsed = ChatRequestSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: "Invalid request", details: parsed.error.issues });
    return;
  }

  const { model, messages, temperature, max_tokens, stream, reasoning } = parsed.data;
  const cfg = MODEL_CONFIGS[model];
  if (!cfg) {
    res.status(400).json({ error: `Unknown model: ${model}`, supported: SUPPORTED_MODELS });
    return;
  }

  const apiKey = process.env[cfg.envKey];
  if (!apiKey) {
    res.status(500).json({ error: `API key not configured for model ${model}. Set env var: ${cfg.envKey}` });
    return;
  }

  try {
    if (cfg.provider === "openrouter") {
      await callOpenRouter(cfg.modelId, apiKey, messages, temperature, max_tokens, reasoning && cfg.reasoning, res, stream);
    } else if (cfg.provider === "nvidia") {
      await callNvidia(cfg.modelId, apiKey, messages, temperature, max_tokens, reasoning && cfg.reasoning, res, stream);
    } else if (cfg.provider === "google") {
      await callGoogle(cfg.modelId, apiKey, messages, max_tokens, res);
    }
  } catch (err) {
    if (!res.headersSent) {
      res.status(502).json({ error: "Upstream AI provider error", detail: String(err) });
    }
  }
});

export default router;

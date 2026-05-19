import { Router, type IRouter } from "express";
import { z } from "zod";

const router: IRouter = Router();

const SUPPORTED_MODELS = [
  "gpt-4o",
  "gpt-4o-mini",
  "gpt-4-turbo",
  "gpt-3.5-turbo",
  "claude-3-5-sonnet-20241022",
  "claude-3-haiku-20240307",
  "gemini-1.5-pro",
] as const;

const ChatRequestSchema = z.object({
  model: z.enum(SUPPORTED_MODELS),
  messages: z.array(
    z.object({
      role: z.enum(["system", "user", "assistant"]),
      content: z.string().min(1),
    }),
  ).min(1),
  temperature: z.number().min(0).max(2).optional().default(0.7),
  max_tokens: z.number().int().min(1).max(16384).optional().default(2048),
  stream: z.boolean().optional().default(false),
});

router.post("/v2/chat/ai", async (req, res) => {
  const parsed = ChatRequestSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      error: "Invalid request",
      details: parsed.error.issues,
    });
    return;
  }

  const { model, messages, temperature, max_tokens } = parsed.data;

  res.status(200).json({
    id: `chatcmpl-${Date.now()}`,
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [
      {
        index: 0,
        message: {
          role: "assistant",
          content: `[${model}] Echo: ${messages[messages.length - 1].content}`,
        },
        finish_reason: "stop",
      },
    ],
    usage: {
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
    },
    meta: {
      temperature,
      max_tokens,
    },
  });
});

export { SUPPORTED_MODELS };
export default router;

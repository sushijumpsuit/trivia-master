// Typed client for the Trivia Master backend. The browser only ever talks to our API,
// never to an LLM provider directly, so no API keys live in the frontend.

export type LastResult = { correct: boolean; answer: string };

export type GameResponse = {
  message: string;
  game_id: string;
  topic: string;
  score: number;
  streak: number;
  best_streak: number;
  question_number: number;
  current_question: string | null;
  last_result: LastResult | null;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data: { detail?: unknown } = await res.json().catch(() => ({}));
    const detail = typeof data.detail === "string" ? data.detail : `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const startGame = (topic: string) => post<GameResponse>("/game/start", { topic });

export const submitAnswer = (gameId: string, answer: string) =>
  post<GameResponse>(`/game/${gameId}/answer`, { answer });

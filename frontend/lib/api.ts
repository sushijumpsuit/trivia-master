// Typed client for the Trivia Master backend. The browser only ever talks to our API,
// never to an LLM provider directly, so no API keys live in the frontend.

export type LastResult = { correct: boolean; answer: string; reaction: string };

export type GameResponse = {
  message: string; // the host's line: round intro after start/next-round, reaction after an answer
  game_id: string;
  topic: string;
  topics: string[];
  round: number; // 1-based
  total_rounds: number;
  questions_per_round: number;
  round_question: number; // questions asked so far in this round (the open one included)
  round_scores: number[];
  score: number;
  streak: number;
  best_streak: number;
  question_number: number;
  current_question: string | null;
  last_result: LastResult | null;
  round_over: boolean;
  finished: boolean;
};

export type GameSettings = { topics: string[]; rounds: number; questions_per_round: number };

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const data: { detail?: unknown } = await res.json().catch(() => ({}));
    const detail = typeof data.detail === "string" ? data.detail : `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const startGame = (settings: GameSettings) => post<GameResponse>("/game/start", settings);

export const submitAnswer = (gameId: string, answer: string) =>
  post<GameResponse>(`/game/${gameId}/answer`, { answer });

export const nextRound = (gameId: string) => post<GameResponse>(`/game/${gameId}/next-round`);

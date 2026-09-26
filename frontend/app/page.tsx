"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { GameResponse, startGame, submitAnswer } from "@/lib/api";

type ChatLine = { from: "host" | "player"; text: string; correct?: boolean };

const SUGGESTIONS = ["90s sitcoms", "Malaysian history", "Space exploration", "Football World Cups"];

export default function Home() {
  const [topic, setTopic] = useState("");
  const [answer, setAnswer] = useState("");
  const [game, setGame] = useState<GameResponse | null>(null);
  const [chat, setChat] = useState<ChatLine[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chatEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat, loading]);

  async function handleStart(e: FormEvent, chosen?: string) {
    e.preventDefault();
    const t = (chosen ?? topic).trim();
    if (!t || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await startGame(t);
      setGame(res);
      setChat([{ from: "host", text: res.message }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function handleAnswer(e: FormEvent) {
    e.preventDefault();
    const a = answer.trim();
    if (!a || !game || loading) return;
    setAnswer("");
    setChat((c) => [...c, { from: "player", text: a }]);
    setLoading(true);
    setError(null);
    try {
      const res = await submitAnswer(game.game_id, a);
      setGame(res);
      setChat((c) => [...c, { from: "host", text: res.message, correct: res.last_result?.correct }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  function newGame() {
    setGame(null);
    setChat([]);
    setTopic("");
    setError(null);
  }

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Trivia Master</h1>
        {game && (
          <button onClick={newGame} className="text-sm text-zinc-500 underline hover:text-zinc-800 dark:hover:text-zinc-200">
            New game
          </button>
        )}
      </header>

      {!game ? (
        <form onSubmit={(e) => handleStart(e)} className="flex flex-col gap-4 rounded-2xl border border-zinc-200 p-6 dark:border-zinc-800">
          <label htmlFor="topic" className="text-lg font-medium">Pick any topic</label>
          <div className="flex gap-2">
            <input
              id="topic"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              maxLength={80}
              placeholder="e.g. organic chemistry"
              className="flex-1 rounded-lg border border-zinc-300 bg-transparent px-3 py-2 dark:border-zinc-700"
            />
            <button disabled={loading || !topic.trim()} className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white disabled:opacity-50">
              {loading ? "Starting..." : "Start"}
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button key={s} type="button" disabled={loading} onClick={(e) => { setTopic(s); handleStart(e, s); }}
                className="rounded-full border border-zinc-300 px-3 py-1 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-900">
                {s}
              </button>
            ))}
          </div>
        </form>
      ) : (
        <div className="grid flex-1 gap-6 md:grid-cols-[1fr_220px]">
          <section className="flex min-h-[420px] flex-col rounded-2xl border border-zinc-200 dark:border-zinc-800">
            <div className="flex-1 space-y-3 overflow-y-auto p-4">
              {chat.map((line, i) => (
                <div key={i} className={line.from === "player" ? "flex justify-end" : "flex justify-start"}>
                  <p className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2 ${
                    line.from === "player"
                      ? "bg-indigo-600 text-white"
                      : line.correct === true
                        ? "bg-emerald-100 text-emerald-950 dark:bg-emerald-950 dark:text-emerald-100"
                        : line.correct === false
                          ? "bg-rose-100 text-rose-950 dark:bg-rose-950 dark:text-rose-100"
                          : "bg-zinc-100 dark:bg-zinc-900"
                  }`}>
                    {line.text}
                  </p>
                </div>
              ))}
              {loading && <p className="text-sm text-zinc-500">The host is thinking...</p>}
              <div ref={chatEnd} />
            </div>
            <form onSubmit={handleAnswer} className="flex gap-2 border-t border-zinc-200 p-3 dark:border-zinc-800">
              <input
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                maxLength={200}
                placeholder="Your answer"
                autoFocus
                className="flex-1 rounded-lg border border-zinc-300 bg-transparent px-3 py-2 dark:border-zinc-700"
              />
              <button disabled={loading || !answer.trim()} className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white disabled:opacity-50">
                Answer
              </button>
            </form>
          </section>

          <aside className="flex flex-col gap-3 rounded-2xl border border-zinc-200 p-4 dark:border-zinc-800">
            <p className="text-sm text-zinc-500">Topic</p>
            <p className="-mt-2 font-medium">{game.topic}</p>
            <Stat label="Score" value={game.score} />
            <Stat label="Streak" value={game.streak} />
            <Stat label="Best streak" value={game.best_streak} />
            <Stat label="Question" value={game.question_number} />
            <Stat label="Difficulty" value={game.difficulty} />
          </aside>
        </div>
      )}

      {error && <p role="alert" className="rounded-lg bg-rose-100 px-4 py-2 text-rose-900 dark:bg-rose-950 dark:text-rose-100">{error}</p>}
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-sm text-zinc-500">{label}</span>
      <span className="text-lg font-semibold capitalize">{value}</span>
    </div>
  );
}

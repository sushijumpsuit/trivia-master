"use client";

import { FormEvent, useState } from "react";
import type { GameSettings } from "@/lib/api";

const SUGGESTIONS = ["Modern Family", "Malaysian history", "Space exploration", "Football World Cups", "90s sitcoms"];
const ROUND_OPTIONS = [1, 2, 3, 4, 5];

type Props = {
  initial?: GameSettings;
  loading: boolean;
  onStart: (settings: GameSettings) => void;
};

export default function SetupScreen({ initial, loading, onStart }: Props) {
  const [rounds, setRounds] = useState(initial?.rounds ?? 3);
  const [perRound, setPerRound] = useState(initial?.questions_per_round ?? 5);
  const [topics, setTopics] = useState<string[]>(() => {
    const t = initial?.topics ?? [];
    return Array.from({ length: 5 }, (_, i) => t[i] ?? "");
  });

  const visible = topics.slice(0, rounds);
  const filled = visible.map((t) => t.trim()).filter(Boolean);
  // Empty rounds repeat the chosen topics in order (same rule as the backend).
  const planned = Array.from({ length: rounds }, (_, i) => filled.length ? filled[i % filled.length] : "");

  function setTopic(i: number, value: string) {
    setTopics((t) => t.map((old, j) => (j === i ? value : old)));
  }

  function applySuggestion(s: string) {
    const empty = visible.findIndex((t) => !t.trim());
    setTopic(empty === -1 ? rounds - 1 : empty, s);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!filled.length || loading) return;
    onStart({ topics: filled, rounds, questions_per_round: perRound });
  }

  return (
    <form onSubmit={submit} className="mx-auto flex w-full max-w-xl flex-col gap-7 px-4 py-10">
      <header className="text-center">
        <h1 className="text-4xl font-bold tracking-tight">Trivia Master</h1>
        <p className="mt-2 text-zinc-500">An AI quiz host that never asks the same question twice.</p>
      </header>

      <section className="flex flex-col gap-2">
        <span className="text-sm font-medium">Rounds</span>
        <div className="grid grid-cols-5 gap-2" role="radiogroup" aria-label="Number of rounds">
          {ROUND_OPTIONS.map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={rounds === n}
              onClick={() => setRounds(n)}
              className={`rounded-xl border py-2 font-semibold transition ${
                rounds === n
                  ? "border-indigo-600 bg-indigo-600 text-white"
                  : "border-zinc-300 hover:border-indigo-400 dark:border-zinc-700"
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <label htmlFor="per-round" className="flex justify-between text-sm font-medium">
          <span>Questions per round</span>
          <span className="tabular-nums text-indigo-600 dark:text-indigo-400">{perRound}</span>
        </label>
        <input
          id="per-round"
          type="range"
          min={3}
          max={20}
          value={perRound}
          onChange={(e) => setPerRound(Number(e.target.value))}
          className="accent-indigo-600"
        />
      </section>

      <section className="flex flex-col gap-3">
        <span className="text-sm font-medium">
          Topics <span className="font-normal text-zinc-500">(empty rounds repeat your topics in order)</span>
        </span>
        {visible.map((t, i) => (
          <div key={i} className="flex items-center gap-3">
            <span className="w-16 shrink-0 text-sm text-zinc-500">Round {i + 1}</span>
            <input
              value={t}
              onChange={(e) => setTopic(i, e.target.value)}
              maxLength={80}
              required={i === 0}
              placeholder={i === 0 ? "e.g. organic chemistry" : planned[i] ? `Repeats: ${planned[i]}` : "Optional"}
              aria-label={`Round ${i + 1} topic`}
              className="flex-1 rounded-xl border border-zinc-300 bg-transparent px-3 py-2 dark:border-zinc-700"
            />
          </div>
        ))}
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => applySuggestion(s)}
              className="rounded-full border border-zinc-300 px-3 py-1 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
            >
              {s}
            </button>
          ))}
        </div>
      </section>

      <button
        disabled={!filled.length || loading}
        className="rounded-2xl bg-indigo-600 py-3 text-lg font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
      >
        {loading ? "Shuffling the deck..." : `Start game (${rounds * perRound} questions)`}
      </button>
    </form>
  );
}

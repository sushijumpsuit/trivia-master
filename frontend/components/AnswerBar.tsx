"use client";

import { FormEvent, RefObject } from "react";
import type { CardPhase } from "./CardStack";

type Props = {
  inputRef: RefObject<HTMLInputElement | null>;
  value: string;
  phase: CardPhase;
  onChange: (v: string) => void;
  onSubmit: () => void; // answering: submit the answer; revealed: throw the card now
};

export default function AnswerBar({ inputRef, value, phase, onChange, onSubmit }: Props) {
  const locked = phase !== "answering";

  function submit(e: FormEvent) {
    e.preventDefault();
    if (phase === "answering" && !value.trim()) return;
    onSubmit();
  }

  return (
    <form
      onSubmit={submit}
      className="fixed inset-x-0 bottom-0 flex justify-center bg-gradient-to-t from-[var(--background)] via-[var(--background)] to-transparent px-4 pb-6 pt-10"
    >
      <div className="flex w-[min(92vw,30rem)] gap-2 rounded-2xl border border-zinc-300 bg-white p-2 shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          readOnly={locked} // stays focusable, so Enter can still throw the card
          maxLength={200}
          autoFocus
          aria-label="Your answer"
          placeholder={phase === "revealed" ? "Press Enter for the next card" : phase === "answering" ? "Type your answer…" : ""}
          className="flex-1 bg-transparent px-3 py-2 outline-none read-only:text-zinc-400"
        />
        <button
          disabled={phase === "checking" || phase === "throwing" || (phase === "answering" && !value.trim())}
          className="rounded-xl bg-indigo-600 px-5 py-2 font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-40"
        >
          {phase === "revealed" ? "Next" : "Answer"}
        </button>
      </div>
    </form>
  );
}

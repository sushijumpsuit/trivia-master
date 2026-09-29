"use client";

import type { LastResult } from "@/lib/api";

export type CardPhase = "answering" | "checking" | "revealed" | "throwing";

type Props = {
  roundKey: number;         // changes per round, so each round gets a fresh stack
  index: number;            // 1-based number of the top card within the round
  total: number;            // questions in the round
  question: string;
  topic: string;
  phase: CardPhase;
  playerAnswer: string;
  result: LastResult | null;
};

const MAX_BEHIND = 2; // cards visible behind the top one

export default function CardStack({ roundKey, index, total, question, topic, phase, playerAnswer, result }: Props) {
  const behind = Math.min(MAX_BEHIND, total - index);
  const throwRight = result?.correct ?? true; // correct cards fly right, wrong ones left

  // Render back cards first so the top card paints last. Keys follow the card number, so when the top
  // card is thrown, the next card keeps its key and animates up from behind.
  const cards = Array.from({ length: behind + 1 }, (_, i) => index + behind - i);

  return (
    <div className="card-scene relative h-[22rem] w-[min(88vw,26rem)] sm:h-[24rem]">
      {cards.map((n) => {
        const depth = n - index;
        const isTop = depth === 0;
        const throwing = isTop && phase === "throwing";
        const transform = throwing
          ? `translateX(${throwRight ? "" : "-"}150vw) rotate(${throwRight ? 30 : -30}deg)`
          : `translate(${depth === 0 ? 0 : depth % 2 ? 10 : -12}px, ${depth * 18}px) scale(${1 - depth * 0.04}) rotate(${depth === 0 ? 0 : depth % 2 ? 4 : -3.5}deg)`;
        return (
          <div
            key={`${roundKey}-${n}`}
            className={`stack-card absolute inset-0 ${throwing ? "is-throwing" : ""}`}
            // No opacity change on the top card: opacity < 1 flattens the 3D flip and both faces show.
            style={{ transform, zIndex: 10 - depth, ...(isTop ? {} : { opacity: 1 - depth * 0.2 }) }}
          >
            {isTop ? (
              <TopCard index={index} total={total} question={question} topic={topic} phase={phase}
                       playerAnswer={playerAnswer} result={result} />
            ) : (
              <CardBack />
            )}
          </div>
        );
      })}
    </div>
  );
}

function CardBack() {
  return (
    <div className="flex h-full w-full items-center justify-center rounded-3xl border border-indigo-300 bg-indigo-600 shadow-xl dark:border-indigo-800 dark:bg-indigo-900">
      <span className="text-6xl font-black text-white/25">?</span>
    </div>
  );
}

function TopCard({ index, total, question, topic, phase, playerAnswer, result }: Omit<Props, "roundKey">) {
  const flipped = (phase === "revealed" || phase === "throwing") && result !== null;
  return (
    <div className={`card-inner relative h-full w-full ${flipped ? "is-flipped" : ""}`}>
      {/* Front: the question */}
      <div className="card-face absolute inset-0 flex flex-col rounded-3xl border border-zinc-200 bg-white p-6 shadow-2xl dark:border-zinc-700 dark:bg-zinc-900">
        <div className="flex items-center justify-between text-sm">
          <span className="rounded-full bg-indigo-50 px-3 py-1 font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
            {topic}
          </span>
          <span className="tabular-nums text-zinc-500">{index} / {total}</span>
        </div>
        <p className="flex flex-1 items-center justify-center text-center text-2xl font-semibold leading-snug">
          {question}
        </p>
        <div className="h-6 text-center text-sm text-zinc-500" aria-live="polite">
          {phase === "checking" && (
            <span className="inline-flex items-center gap-1">
              Checking
              <span className="pulse-dot">.</span>
              <span className="pulse-dot [animation-delay:0.2s]">.</span>
              <span className="pulse-dot [animation-delay:0.4s]">.</span>
            </span>
          )}
        </div>
      </div>

      {/* Back: the result */}
      <div
        className={`card-face card-back absolute inset-0 flex flex-col items-center justify-center gap-3 rounded-3xl p-6 text-center shadow-2xl ${
          result?.correct
            ? "bg-emerald-500 text-white dark:bg-emerald-700"
            : "bg-rose-500 text-white dark:bg-rose-700"
        }`}
        aria-live="assertive"
      >
        {result && (
          <>
            <div className="flex flex-1 flex-col items-center justify-center gap-3">
              <span className="text-6xl" aria-hidden>{result.correct ? "✓" : "✗"}</span>
              <span className="text-2xl font-bold">{result.correct ? "Correct!" : "Not quite"}</span>
              {!result.correct && (
                <>
                  <span className="text-sm opacity-80">You said: <span className="line-through">{playerAnswer}</span></span>
                  <span className="text-lg">Answer: <span className="font-semibold">{result.answer}</span></span>
                </>
              )}
              {result.reaction && <p className="mt-2 text-sm italic opacity-90">“{result.reaction}”</p>}
            </div>
            <span className="text-xs opacity-70">Press Enter for the next card</span>
          </>
        )}
      </div>
    </div>
  );
}

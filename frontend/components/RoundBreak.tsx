import type { GameResponse } from "@/lib/api";

type Props = { game: GameResponse; loading: boolean; onNext: () => void };

export default function RoundBreak({ game, loading, onNext }: Props) {
  const got = game.round_scores[game.round - 1];
  const nextTopic = game.topics[game.round]; // round is 1-based, so this is the next round's topic
  return (
    <section className="mx-auto flex w-full max-w-md flex-col items-center gap-5 px-4 py-16 text-center">
      <p className="text-sm uppercase tracking-widest text-zinc-500">Round {game.round} complete</p>
      <p className="text-6xl font-bold tabular-nums">
        {got}<span className="text-3xl text-zinc-400"> / {game.questions_per_round}</span>
      </p>
      <p className="text-zinc-500">Total score: {game.score}</p>
      <div className="mt-4 rounded-2xl border border-zinc-200 px-6 py-4 dark:border-zinc-800">
        <p className="text-sm text-zinc-500">Next up · Round {game.round + 1}</p>
        <p className="text-xl font-semibold">{nextTopic}</p>
      </div>
      <button
        onClick={onNext}
        disabled={loading}
        autoFocus
        className="rounded-2xl bg-indigo-600 px-8 py-3 text-lg font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
      >
        {loading ? "Shuffling the deck..." : `Start round ${game.round + 1}`}
      </button>
    </section>
  );
}

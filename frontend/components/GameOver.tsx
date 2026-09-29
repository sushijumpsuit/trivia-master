import type { GameResponse } from "@/lib/api";

type Props = { game: GameResponse; loading: boolean; onPlayAgain: () => void; onNewSetup: () => void };

export default function GameOver({ game, loading, onPlayAgain, onNewSetup }: Props) {
  const total = game.total_rounds * game.questions_per_round;
  return (
    <section className="mx-auto flex w-full max-w-md flex-col items-center gap-6 px-4 py-14 text-center">
      <p className="text-sm uppercase tracking-widest text-zinc-500">Game over</p>
      <p className="text-7xl font-bold tabular-nums">
        {game.score}<span className="text-3xl text-zinc-400"> / {total}</span>
      </p>
      <p className="text-zinc-500">Best streak: {game.best_streak}</p>

      <ul className="flex w-full flex-col gap-3">
        {game.topics.map((topic, i) => {
          const got = game.round_scores[i];
          return (
            <li key={i} className="flex flex-col gap-1 text-left">
              <div className="flex justify-between text-sm">
                <span>Round {i + 1} · <span className="text-zinc-500">{topic}</span></span>
                <span className="tabular-nums">{got}/{game.questions_per_round}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
                <div className="h-full rounded-full bg-emerald-500" style={{ width: `${(got / game.questions_per_round) * 100}%` }} />
              </div>
            </li>
          );
        })}
      </ul>

      <div className="flex gap-3">
        <button
          onClick={onPlayAgain}
          disabled={loading}
          autoFocus
          className="rounded-2xl bg-indigo-600 px-6 py-3 font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
        >
          {loading ? "Shuffling..." : "Play again"}
        </button>
        <button
          onClick={onNewSetup}
          className="rounded-2xl border border-zinc-300 px-6 py-3 font-semibold hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
        >
          New setup
        </button>
      </div>
    </section>
  );
}

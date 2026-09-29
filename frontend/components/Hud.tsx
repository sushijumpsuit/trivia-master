import type { GameResponse } from "@/lib/api";

export default function Hud({ game, cardIndex, answered }: { game: GameResponse; cardIndex: number; answered: boolean }) {
  // Cards finished this round: the ones before the top card, plus the top one once it's been answered.
  const progress = Math.min(1, (cardIndex - 1 + (answered ? 1 : 0)) / game.questions_per_round);
  return (
    <header className="mx-auto w-full max-w-3xl px-4 pt-5">
      <div className="flex items-center justify-between gap-4 text-sm">
        <span className="font-medium">
          Round {game.round}/{game.total_rounds} <span className="text-zinc-500">· {game.topic}</span>
        </span>
        <span className="flex gap-4 tabular-nums">
          <span>Score <b>{game.score}</b></span>
          <span className={game.streak >= 2 ? "text-orange-500" : ""}>
            Streak <b>{game.streak}</b>{game.streak >= 3 ? " 🔥" : ""}
          </span>
        </span>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800" aria-hidden>
        <div className="h-full rounded-full bg-indigo-600 transition-all duration-500" style={{ width: `${progress * 100}%` }} />
      </div>
    </header>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import AnswerBar from "@/components/AnswerBar";
import CardStack, { type CardPhase } from "@/components/CardStack";
import GameOver from "@/components/GameOver";
import Hud from "@/components/Hud";
import RoundBreak from "@/components/RoundBreak";
import SetupScreen from "@/components/SetupScreen";
import { GameResponse, GameSettings, LastResult, nextRound, startGame, submitAnswer } from "@/lib/api";

type Screen = "setup" | "playing" | "roundBreak" | "gameOver";
type Card = { question: string; index: number; roundKey: number };

const AUTO_THROW_MS = 2500; // how long the result stays visible before the card flies away
const THROW_MS = 550;       // must match .stack-card.is-throwing in globals.css

export default function Home() {
  const [screen, setScreen] = useState<Screen>("setup");
  const [settings, setSettings] = useState<GameSettings | undefined>();
  const [game, setGame] = useState<GameResponse | null>(null);
  const [card, setCard] = useState<Card | null>(null);
  const [phase, setPhase] = useState<CardPhase>("answering");
  const [answer, setAnswer] = useState("");
  const [playerAnswer, setPlayerAnswer] = useState("");
  const [result, setResult] = useState<LastResult | null>(null);
  const [hostLine, setHostLine] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Refs hold the latest values for timers and key presses (state inside a timer would be stale).
  const inputRef = useRef<HTMLInputElement>(null);
  const phaseRef = useRef<CardPhase>("answering");
  const gameRef = useRef<GameResponse | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach(clearTimeout);
  }, []);

  function go(p: CardPhase) {
    phaseRef.current = p;
    setPhase(p);
  }

  function later(fn: () => void, ms: number) {
    timers.current.push(setTimeout(fn, ms));
  }

  function clearTimers() {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }

  function focusInput() {
    later(() => inputRef.current?.focus(), 0);
  }

  function showRound(res: GameResponse) {
    gameRef.current = res;
    setGame(res);
    setCard({ question: res.current_question ?? "", index: res.round_question, roundKey: res.round });
    setHostLine(res.message);
    setResult(null);
    setAnswer("");
    go("answering");
    setScreen("playing");
    focusInput();
  }

  async function begin(s: GameSettings) {
    setSettings(s);
    setLoading(true);
    setError(null);
    try {
      showRound(await startGame(s));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function startNextRound() {
    if (!game) return;
    setLoading(true);
    setError(null);
    try {
      showRound(await nextRound(game.game_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function checkAnswer() {
    if (!game || phaseRef.current !== "answering") return;
    const a = answer.trim();
    setPlayerAnswer(a);
    setError(null);
    go("checking");
    try {
      const res = await submitAnswer(game.game_id, a);
      gameRef.current = res;
      setGame(res);
      setResult(res.last_result);
      setHostLine("");
      go("revealed"); // the card flips
      later(throwCard, AUTO_THROW_MS);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      go("answering");
      focusInput();
    }
  }

  function throwCard() {
    if (phaseRef.current !== "revealed") return; // Enter and the timer can both fire; act once
    clearTimers();
    go("throwing");
    later(() => {
      const g = gameRef.current;
      if (!g) return;
      if (g.finished) return setScreen("gameOver");
      if (g.round_over) return setScreen("roundBreak");
      setCard({ question: g.current_question ?? "", index: g.round_question, roundKey: g.round });
      setResult(null);
      setAnswer("");
      go("answering");
      focusInput();
    }, THROW_MS);
  }

  function onAnswerBarSubmit() {
    if (phaseRef.current === "answering") void checkAnswer();
    else if (phaseRef.current === "revealed") throwCard();
  }

  return (
    <main className="flex min-h-screen w-full flex-col">
      {error && (
        <p role="alert" className="fixed inset-x-0 top-3 z-50 mx-auto w-fit max-w-[90vw] rounded-xl bg-rose-600 px-4 py-2 text-sm text-white shadow-lg">
          {error}
        </p>
      )}

      {screen === "setup" && <SetupScreen initial={settings} loading={loading} onStart={begin} />}

      {screen === "playing" && game && card && (
        <>
          <Hud game={game} cardIndex={card.index} answered={phase === "revealed" || phase === "throwing"} />
          <p className="mx-auto mt-4 h-10 max-w-xl px-4 text-center text-sm italic text-zinc-500">
            {hostLine && <>🎙️ {hostLine}</>}
          </p>
          <div className="flex flex-1 items-center justify-center overflow-x-hidden pb-36 pt-2">
            <CardStack
              roundKey={card.roundKey}
              index={card.index}
              total={game.questions_per_round}
              question={card.question}
              topic={game.topic}
              phase={phase}
              playerAnswer={playerAnswer}
              result={result}
            />
          </div>
          <AnswerBar inputRef={inputRef} value={answer} phase={phase} onChange={setAnswer} onSubmit={onAnswerBarSubmit} />
        </>
      )}

      {screen === "roundBreak" && game && <RoundBreak game={game} loading={loading} onNext={startNextRound} />}

      {screen === "gameOver" && game && (
        <GameOver
          game={game}
          loading={loading}
          onPlayAgain={() => settings && begin(settings)}
          onNewSetup={() => setScreen("setup")}
        />
      )}
    </main>
  );
}

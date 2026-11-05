"use client";

import { useCallback, useRef, useState } from "react";
import type { SessionResult } from "./types";

export type SessionStatus = "idle" | "loading" | "error";

type Answers = Readonly<Record<string, string>>;

async function fetchSession(prompt: string, answers: Answers): Promise<SessionResult> {
  const response = await fetch("/backend/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, answers }),
  });
  if (!response.ok) {
    throw new Error(`サーバーが要求を処理できませんでした（${response.status}）`);
  }
  return (await response.json()) as SessionResult;
}

/** The session is recomputed by the API from the request and all answers on every change. */
export function useSession() {
  const [prompt, setPrompt] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
  const [result, setResult] = useState<SessionResult | null>(null);
  const [status, setStatus] = useState<SessionStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const latestRequest = useRef(0);

  const load = useCallback(async (nextPrompt: string, nextAnswers: Answers) => {
    latestRequest.current += 1;
    const request = latestRequest.current;
    setStatus("loading");
    setError(null);
    try {
      const next = await fetchSession(nextPrompt, nextAnswers);
      if (request !== latestRequest.current) return;
      setResult(next);
      setStatus("idle");
    } catch (cause) {
      if (request !== latestRequest.current) return;
      const message = cause instanceof Error ? cause.message : "通信に失敗しました";
      setError(`${message}。API が起動しているか確認してください。`);
      setStatus("error");
    }
  }, []);

  const submit = useCallback(
    (text: string) => {
      setPrompt(text);
      setAnswers({});
      void load(text, {});
    },
    [load],
  );

  const answer = useCallback(
    (questionId: string, text: string) => {
      if (prompt === null) return;
      const nextAnswers = { ...answers, [questionId]: text };
      setAnswers(nextAnswers);
      void load(prompt, nextAnswers);
    },
    [answers, load, prompt],
  );

  const reset = useCallback(() => {
    latestRequest.current += 1;
    setPrompt(null);
    setAnswers({});
    setResult(null);
    setStatus("idle");
    setError(null);
  }, []);

  return { prompt, result, status, error, submit, answer, reset };
}

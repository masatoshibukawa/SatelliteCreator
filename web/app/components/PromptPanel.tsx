"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import type { SessionStatus } from "../lib/useSession";
import type { Question, SessionResult } from "../lib/types";

const EXAMPLES: readonly string[] = [
  "高度 400 km、軌道傾斜角 51.6 度の 3U CubeSat で光通信を実証したい",
  "6U の衛星で地球を撮影して、農地の変化を観測したい",
  "小型衛星で大気の密度を測りたい",
];

interface PromptPanelProps {
  prompt: string | null;
  result: SessionResult | null;
  status: SessionStatus;
  error: string | null;
  onSubmit: (text: string) => void;
  onAnswer: (questionId: string, text: string) => void;
  onReset: () => void;
}

function RequestForm({ busy, onSubmit }: { busy: boolean; onSubmit: (text: string) => void }) {
  const [text, setText] = useState("");

  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (text.trim() !== "") onSubmit(text.trim());
  };

  return (
    <form className="prompt-form" onSubmit={submit}>
      <p className="prompt-lead">何を実現したい衛星ですか。ふつうの文章で書いてください。</p>
      <div className="examples">
        {EXAMPLES.map((example) => (
          <button key={example} type="button" className="chip-example" onClick={() => setText(example)}>
            {example}
          </button>
        ))}
      </div>
      <label className="sr-only" htmlFor="request-text">
        衛星への要求
      </label>
      <textarea
        id="request-text"
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="例：高度 500 km の 3U 衛星で、森林の変化を観測したい"
        rows={5}
        maxLength={4000}
      />
      <button type="submit" className="btn btn-primary" disabled={busy || text.trim() === ""}>
        要求を送る
      </button>
    </form>
  );
}

function AnswerForm({
  question,
  busy,
  onAnswer,
}: {
  question: Question;
  busy: boolean;
  onAnswer: (questionId: string, text: string) => void;
}) {
  const [text, setText] = useState("");

  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (text.trim() === "") return;
    onAnswer(question.id, text.trim());
    setText("");
  };

  return (
    <form className="msg msg-question" onSubmit={submit}>
      <span className="msg-role">質問</span>
      <label htmlFor="answer-text">{question.text}</label>
      {question.unreadable && (
        <p className="msg-warning">「{question.answer}」は読み取れないか、対応していません。もう一度お願いします。</p>
      )}
      <textarea
        id="answer-text"
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={2}
        maxLength={2000}
      />
      <button type="submit" className="btn btn-primary btn-small" disabled={busy || text.trim() === ""}>
        回答する
      </button>
    </form>
  );
}

export default function PromptPanel({ prompt, result, status, error, onSubmit, onAnswer, onReset }: PromptPanelProps) {
  const logRef = useRef<HTMLDivElement | null>(null);
  const busy = status === "loading";
  const questions = result?.questions ?? [];
  const answered = questions.filter((question) => question.answered);
  const next = questions.find((question) => !question.answered) ?? null;

  useEffect(() => {
    const log = logRef.current;
    if (log !== null) log.scrollTop = log.scrollHeight;
  }, [answered.length, next?.id]);

  if (prompt === null) {
    return (
      <section className="panel chat" aria-label="要求の入力">
        <RequestForm busy={busy} onSubmit={onSubmit} />
        {error !== null && <p className="msg-error">{error}</p>}
      </section>
    );
  }

  return (
    <section className="panel chat" aria-label="要求の入力">
      <div className="chat-log" ref={logRef}>
        <div className="msg msg-user">
          <span className="msg-role">あなたの要求</span>
          <span>{prompt}</span>
        </div>
        {answered.map((question) => (
          <div key={question.id} className="msg msg-answered">
            <span className="msg-role">{question.from_prompt ? "要求から読み取り" : "回答済み"}</span>
            <span className="msg-question-text">{question.text}</span>
            <span>{question.answer}</span>
          </div>
        ))}
        {result?.refusal ? <p className="msg-error">{result.refusal}</p> : null}
        {next !== null && <AnswerForm key={next.id} question={next} busy={busy} onAnswer={onAnswer} />}
        {result !== null && !result.refusal && next === null && (
          <p className="msg msg-done">質問はすべて回答済みです。</p>
        )}
        {error !== null && <p className="msg-error">{error}</p>}
      </div>
      <div className="chat-footer">
        {questions.length > 0 && (
          <span className="muted">
            回答 {answered.length} / {questions.length}
          </span>
        )}
        <button type="button" className="btn btn-small" onClick={onReset}>
          最初からやり直す
        </button>
      </div>
    </section>
  );
}

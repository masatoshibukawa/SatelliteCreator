"use client";

import type { DesignDocument, Section, SectionState } from "../lib/types";

const STATE_LABEL: Record<SectionState, string> = {
  filled: "記載済み",
  partial: "一部記載",
  pending: "未計算",
};

function StateChip({ state }: { state: SectionState }) {
  return <span className={`state-chip state-${state}`}>{STATE_LABEL[state]}</span>;
}

function saveFile(name: string, text: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

function Chapter({ section }: { section: Section }) {
  return (
    <article className="chapter">
      <header>
        <h3>
          <span className="chapter-number">{section.number}</span>
          {section.title}
        </h3>
        <StateChip state={section.state} />
      </header>
      {section.lines.length > 0 && (
        <ul>
          {section.lines.map((line, index) => (
            <li key={`${index}-${line}`}>{line}</li>
          ))}
        </ul>
      )}
      {section.pending_note !== "" && <p className="chapter-note">{section.pending_note}</p>}
    </article>
  );
}

interface DocumentPanelProps {
  document: DesignDocument | null;
  launchRequest: Record<string, unknown> | null;
}

export default function DocumentPanel({ document: designDocument, launchRequest }: DocumentPanelProps) {
  if (designDocument === null) {
    return (
      <section className="panel document" aria-label="設計書">
        <h2 className="panel-title">設計書</h2>
        <p className="document-empty">要求を送ると、ここに設計書を作ります。</p>
      </section>
    );
  }

  const covered = designDocument.checklist.filter((item) => item.state !== "pending").length;

  return (
    <section className="panel document" aria-label="設計書">
      <div className="panel-header">
        <h2 className="panel-title">設計書</h2>
        <div className="panel-actions">
          {launchRequest !== null && (
            <button
              type="button"
              className="btn btn-small"
              onClick={() =>
                saveFile("launch_request.json", `${JSON.stringify(launchRequest, null, 2)}\n`, "application/json")
              }
            >
              ロケットへ渡す JSON を保存
            </button>
          )}
          <button
            type="button"
            className="btn btn-small"
            onClick={() => saveFile("design-document.md", designDocument.markdown, "text/markdown")}
          >
            Markdown で保存
          </button>
        </div>
      </div>
      <div className="document-body">
        <p className="document-title">{designDocument.title}</p>
        {designDocument.sections.map((section) => (
          <Chapter key={section.number} section={section} />
        ))}
        <details className="checklist">
          <summary>
            募集要項の記載項目 {covered} / {designDocument.checklist.length}
          </summary>
          <ol>
            {designDocument.checklist.map((item) => (
              <li key={item.number}>
                <span>{item.label}</span>
                <StateChip state={item.state} />
              </li>
            ))}
          </ol>
        </details>
      </div>
    </section>
  );
}

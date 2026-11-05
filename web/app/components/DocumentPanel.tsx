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

function saveMarkdown(document_: DesignDocument): void {
  const url = URL.createObjectURL(new Blob([document_.markdown], { type: "text/markdown" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "design-document.md";
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

export default function DocumentPanel({ document: designDocument }: { document: DesignDocument | null }) {
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
        <button type="button" className="btn btn-small" onClick={() => saveMarkdown(designDocument)}>
          Markdown で保存
        </button>
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
        <div className="references">
          <h3>出典</h3>
          <ul>
            {designDocument.references.map((item) => (
              <li key={item.url}>
                <a href={item.url} target="_blank" rel="noreferrer">
                  {item.title}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

import type { Finding, ReviewState, ReviewView } from "../lib/types";

const STATE_LABEL: Record<ReviewState, string> = {
  passed: "確認済み",
  blocked: "未確認",
  waiting: "待ち",
};
const VISIBLE_FINDINGS = 4;

function findingText(finding: Finding): string {
  return finding.subject ? `${finding.subject}: ${finding.message}` : finding.message;
}

export default function ReviewStrip({ reviews, scopeFindings }: { reviews: ReviewView[]; scopeFindings: Finding[] }) {
  const blocked = reviews.find((item) => item.state === "blocked");
  const findings = blocked?.findings ?? [];
  const hidden = findings.length - VISIBLE_FINDINGS;

  return (
    <section className="panel reviews" aria-label="工程の確認">
      <h2 className="panel-title">工程の確認</h2>
      <p className="review-caption">
        要求がそろい、つながっているかの自動確認です。設計の妥当性はまだ判定していません。
      </p>
      <ol className="review-steps">
        {reviews.map((item) => (
          <li key={item.review} className={`review-step review-${item.state}`}>
            <strong>{item.review}</strong>
            <span>{STATE_LABEL[item.state]}</span>
          </li>
        ))}
      </ol>
      {reviews.length === 0 && <p className="muted">要求を送ると、工程の状況を表示します。</p>}
      {scopeFindings.map((item) => (
        <p key={item.code} className="msg-warning">
          {item.message}
        </p>
      ))}
      {blocked && (
        <div className="review-findings">
          <p>{blocked.review} の確認を終えるには、次の解決が必要です。</p>
          <ul>
            {findings.slice(0, VISIBLE_FINDINGS).map((item) => (
              <li key={`${item.code}-${item.subject}`}>{findingText(item)}</li>
            ))}
          </ul>
          {hidden > 0 && <p className="muted">ほか {hidden} 件</p>}
        </div>
      )}
    </section>
  );
}

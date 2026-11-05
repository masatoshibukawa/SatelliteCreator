import type { BlockState, BlockStatus, CheckResult } from "../lib/types";

const STATE_LABEL: Record<BlockState, string> = {
  done: "計算済み",
  waiting: "入力待ち",
  not_built: "未実装",
};

export default function SimulationPanel({ blocks, checks }: { blocks: BlockStatus[]; checks: CheckResult[] }) {
  const finished = checks.filter((item) => item.state !== "not_run").length;
  const failed = checks.filter((item) => item.state === "failed");

  return (
    <section className="panel simulation" aria-label="シミュレーションの状況">
      <h2 className="panel-title">シミュレーションの状況</h2>
      {blocks.length === 0 && <p className="muted">要求を送ると、計算の状況を表示します。</p>}
      <ul className="block-list">
        {blocks.map((item) => (
          <li key={item.block} className="block-row">
            <span className="block-name">{item.label}</span>
            <span className={`block-state block-${item.state}`}>{STATE_LABEL[item.state]}</span>
            {item.values.length > 0 && (
              <span className="block-values">
                {item.values.map((value) => `${value.label} ${value.text}`).join("、")}
              </span>
            )}
            {item.note !== "" && <span className="block-note">{item.note}</span>}
          </li>
        ))}
      </ul>
      {checks.length > 0 && (
        <p className="muted">
          整合チェック {finished} / {checks.length} 件を実行済み
        </p>
      )}
      {failed.map((item) => (
        <p key={item.id} className="msg-warning">
          不整合: {item.label}
          {item.provisional ? "（暫定の判定）" : ""}
        </p>
      ))}
    </section>
  );
}

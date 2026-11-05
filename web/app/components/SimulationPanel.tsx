import type { BlockState, BlockStatus, CheckResult, DesignLoop, LoopStatus } from "../lib/types";

const STATE_LABEL: Record<BlockState, string> = {
  done: "計算済み",
  waiting: "入力待ち",
  not_built: "未実装",
};

const LOOP_LABEL: Record<LoopStatus, string> = {
  converged: "すべての確認に合格",
  no_solution: "解決策が見つかりません",
  limit_reached: "反復の上限に到達",
  needs_input: "入力待ち",
};

interface SimulationPanelProps {
  blocks: BlockStatus[];
  checks: CheckResult[];
  loop: DesignLoop | null;
}

export default function SimulationPanel({ blocks, checks, loop }: SimulationPanelProps) {
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
      {loop !== null && (
        <div className="loop-log">
          <p>
            反復 {loop.iterations.length} 回: {LOOP_LABEL[loop.status]}
          </p>
          <ol>
            {loop.iterations.flatMap((record) =>
              record.messages.map((message, index) => (
                <li key={`${record.number}-${index}`}>
                  {message.agent}: {message.text}
                </li>
              )),
            )}
          </ol>
        </div>
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

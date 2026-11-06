"use client";

import { useState } from "react";
import DocumentPanel from "./components/DocumentPanel";
import EquipmentPanel from "./components/EquipmentPanel";
import GroundDiagram from "./components/GroundDiagram";
import LayoutView from "./components/LayoutView";
import OrbitViewer from "./components/OrbitViewer";
import PowerDiagram from "./components/PowerDiagram";
import PromptPanel from "./components/PromptPanel";
import ReviewStrip from "./components/ReviewStrip";
import SatelliteViewer from "./components/SatelliteViewer";
import SimulationPanel from "./components/SimulationPanel";
import TimelineView from "./components/TimelineView";
import { useSession } from "./lib/useSession";

const TABS = [
  { id: "document", label: "設計書" },
  { id: "analysis", label: "解析の状況" },
] as const;

const VIEWS = [
  { id: "overview", label: "全体" },
  { id: "layout", label: "機器配置" },
  { id: "timeline", label: "時系列" },
] as const;

type Tab = (typeof TABS)[number]["id"];
type View = (typeof VIEWS)[number]["id"];

export default function Home() {
  const { prompt, result, status, error, submit, answer, chooseEquipment, reset } = useSession();
  const [tab, setTab] = useState<Tab>("document");
  const [view, setView] = useState<View>("overview");
  const diagrams = result?.diagrams ?? null;

  return (
    <main className="app">
      <header className="status-strip">
        <h1>SatelliteCreator</h1>
        <span className="muted">要求から衛星の設計書を作る</span>
      </header>
      <div className="app-columns">
        <div className="column column-prompt">
          <PromptPanel
            prompt={prompt}
            result={result}
            status={status}
            error={error}
            onSubmit={submit}
            onAnswer={answer}
            onReset={reset}
          />
          <EquipmentPanel
            categories={result?.equipment ?? []}
            busy={status === "loading"}
            onChoose={chooseEquipment}
          />
        </div>
        <div className="column column-center">
          <div className="column-tabs" role="tablist" aria-label="中央の表示">
            {VIEWS.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                className="btn btn-small"
                aria-selected={view === item.id}
                onClick={() => setView(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          {view === "overview" && (
            <div className="stage-grid">
              <SatelliteViewer satellite={result?.satellite ?? null} equipment={result?.equipment ?? []} />
              <OrbitViewer diagrams={diagrams} />
              <PowerDiagram diagrams={diagrams} />
              <GroundDiagram diagrams={diagrams} />
            </div>
          )}
          {view === "layout" && <LayoutView satellite={result?.satellite ?? null} layout={result?.layout ?? null} />}
          {view === "timeline" && <TimelineView timeline={result?.timeline ?? null} />}
          <ReviewStrip reviews={result?.reviews ?? []} scopeFindings={result?.scope_findings ?? []} />
        </div>
        <div className="column column-document">
          <div className="column-tabs" role="tablist" aria-label="右の表示">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                className="btn btn-small"
                aria-selected={tab === item.id}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          {tab === "document" ? (
            <DocumentPanel document={result?.document ?? null} launchRequest={result?.launch_request ?? null} />
          ) : (
            <SimulationPanel
              blocks={result?.simulations ?? []}
              checks={result?.checks ?? []}
              loop={result?.iteration ?? null}
            />
          )}
        </div>
      </div>
    </main>
  );
}

"use client";

import DocumentPanel from "./components/DocumentPanel";
import PromptPanel from "./components/PromptPanel";
import ReviewStrip from "./components/ReviewStrip";
import SatelliteViewer from "./components/SatelliteViewer";
import SimulationPanel from "./components/SimulationPanel";
import { useSession } from "./lib/useSession";

export default function Home() {
  const { prompt, result, status, error, submit, answer, reset } = useSession();

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
        </div>
        <div className="column column-center">
          <SatelliteViewer satellite={result?.satellite ?? null} />
          <SimulationPanel blocks={result?.simulations ?? []} checks={result?.checks ?? []} />
          <ReviewStrip reviews={result?.reviews ?? []} scopeFindings={result?.scope_findings ?? []} />
        </div>
        <div className="column column-document">
          <DocumentPanel document={result?.document ?? null} launchRequest={result?.launch_request ?? null} />
        </div>
      </div>
    </main>
  );
}

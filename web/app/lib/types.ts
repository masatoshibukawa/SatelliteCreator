/** Mirrors the response of POST /session (satellitecreator/session.py). */

export type SectionState = "filled" | "partial" | "pending";
export type ReviewState = "passed" | "blocked" | "waiting";
export type RequirementStatus = "confirmed" | "assumed" | "open";

export interface Finding {
  code: string;
  message: string;
  subject: string;
}

export interface Question {
  id: string;
  text: string;
  answer: string;
  from_prompt: boolean;
  unreadable: boolean;
  answered: boolean;
}

export interface ReviewView {
  review: string;
  phase: string;
  state: ReviewState;
  outputs: string[];
  findings: Finding[];
}

export interface SatelliteView {
  form_factor: string;
  width_m: number;
  depth_m: number;
  length_m: number;
  max_mass_kg: number;
}

export interface Section {
  number: string;
  title: string;
  state: SectionState;
  lines: string[];
  pending_note: string;
}

export interface ChecklistItem {
  number: number;
  label: string;
  state: SectionState;
}

export interface Reference {
  title: string;
  url: string;
}

export interface DesignDocument {
  title: string;
  sections: Section[];
  checklist: ChecklistItem[];
  references: Reference[];
  markdown: string;
}

export type BlockState = "done" | "waiting" | "not_built";
export type CheckState = "passed" | "failed" | "not_run";

export interface DisplayValue {
  label: string;
  text: string;
}

export interface BlockStatus {
  block: string;
  label: string;
  state: BlockState;
  values: DisplayValue[];
  note: string;
}

export interface CheckResult {
  id: string;
  label: string;
  block: string;
  state: CheckState;
  missing: string[];
  provisional: boolean;
}

export type LoopStatus = "converged" | "no_solution" | "limit_reached" | "needs_input";

export interface IterationRecord {
  number: number;
  messages: { agent: string; text: string }[];
}

export interface DesignLoop {
  status: LoopStatus;
  iterations: IterationRecord[];
  questions: string[];
}

export interface SessionResult {
  refusal: string;
  questions: Question[];
  reviews: ReviewView[];
  simulations: BlockStatus[];
  checks: CheckResult[];
  satellite: SatelliteView | null;
  scope_findings: Finding[];
  document: DesignDocument | null;
  launch_request: Record<string, unknown> | null;
  iteration: DesignLoop | null;
}

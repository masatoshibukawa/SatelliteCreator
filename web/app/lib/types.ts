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
  assumed: boolean;
  unreadable: boolean;
  answered: boolean;
  options: string[];
}

export interface ReviewView {
  review: string;
  phase: string;
  state: ReviewState;
  provisional: boolean;
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

export interface DesignDocument {
  title: string;
  sections: Section[];
  checklist: ChecklistItem[];
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

export interface EquipmentChoice {
  id: string;
  label: string;
  mass_g: number;
  average_power_mw: number;
  provisional: boolean;
}

export interface EquipmentCategory {
  id: string;
  label: string;
  selected: string;
  options: EquipmentChoice[];
}

/** A value stays null until the design core has calculated it. */
export interface DiagramData {
  altitude_m: number | null;
  inclination_deg: number | null;
  orbit_period_s: number | null;
  max_eclipse_s: number | null;
  min_sunlight_s: number | null;
  usable_sunlit_power_w: number | null;
  average_consumed_power_w: number | null;
  orbit_generated_energy_j: number | null;
  orbit_consumed_energy_j: number | null;
  battery_depth_of_discharge_ratio: number | null;
  link_margin_db: number | null;
  slant_range_m: number | null;
  min_elevation_deg: number | null;
  downlink_frequency_hz: number | null;
  downlink_rate_bps: number | null;
  provisional: boolean;
}

export interface LayoutItem {
  id: string;
  label: string;
  group: string;
  role: string;
  mass_g: number | null;
  average_power_w: number | null;
  size_mm: [number, number, number];
  center_mm: [number, number, number];
  external: boolean;
}

export interface SatelliteLayout {
  items: LayoutItem[];
  stack_height_mm: number;
  internal_length_mm: number;
}

export interface ContactWindow {
  start_s: number;
  end_s: number;
  max_elevation_deg: number;
  downlink_bit: number;
}

export interface Timeline {
  station: string;
  time_s: number[];
  generated_power_w: number[];
  consumed_power_w: number[];
  battery_ratio: number[];
  link_margin_db: (number | null)[];
  downlinked_bit: number[];
  contacts: ContactWindow[];
  contact_s: number;
  downlink_bit: number;
  min_battery_ratio: number;
}

export interface SessionResult {
  refusal: string;
  questions: Question[];
  reviews: ReviewView[];
  simulations: BlockStatus[];
  checks: CheckResult[];
  satellite: SatelliteView | null;
  equipment: EquipmentCategory[];
  diagrams: DiagramData;
  layout: SatelliteLayout | null;
  layout_fits: boolean;
  timeline: Timeline | null;
  scope_findings: Finding[];
  document: DesignDocument | null;
  launch_request: Record<string, unknown> | null;
  iteration: DesignLoop | null;
}

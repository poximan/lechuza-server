export type IncidentFilter = "potential" | "active" | "all";
export type IncidentStatus = "potential" | "active" | "recovering" | "resolved";
export type DispatchStatus = "pending" | "processing" | "sent" | "failed";

export interface Incident {
  incident_id: string;
  alarm_key: string;
  title: string;
  category: string;
  status: IncidentStatus;
  active: number;
  notified: number;
  expected_clearance_minutes: number;
  first_seen_at: string;
  last_seen_at: string;
  qualified_at: string | null;
  notified_at: string | null;
  recovery_started_at: string | null;
  resolved_at: string | null;
  last_event_type: string;
  recipients: string[];
  dispatch_status: DispatchStatus | null;
  dispatch_updated_at: string | null;
  dispatch_error: string | null;
}

export interface IncidentCounts {
  potential: number;
  active: number;
  recovering: number;
  resolved: number;
}

export interface AlarmConditionCounts {
  active: number;
  inactive: number;
  unknown: number;
}

export interface FrequentIncident {
  source_id: string;
  alarm_key: string;
  title: string;
  category: string;
  total: number;
  daily: number;
  weekly: number;
  monthly: number;
  annual: number;
}

export interface ClearanceMetric {
  source_id: string;
  alarm_key: string;
  title: string;
  category: string;
  configured_minutes: number;
  active_sample_count: number;
  median_active_minutes: number | null;
  p90_active_minutes: number | null;
  inactive_sample_count: number;
  median_inactive_minutes: number | null;
  p90_inactive_minutes: number | null;
}

export interface Dashboard {
  counts: IncidentCounts;
  conditions: AlarmConditionCounts;
  frequent: FrequentIncident[];
  clearance: ClearanceMetric[];
}

export interface SyncStatus {
  state: "starting" | "ok" | "degraded";
  last_success_at: string | null;
  last_error: string | null;
}

export interface HealthStatus {
  status: "ok" | "degraded";
  generated_at: string;
  sync: SyncStatus;
}

export interface AlarmeroSnapshot {
  incidents: Incident[];
  dashboard: Dashboard;
  health: HealthStatus;
}

export interface AlarmCatalogItem {
  source_id: string;
  alarm_key: string;
  title: string;
  category: string;
  activation_seconds: number;
  recovery_seconds: number;
  send_start: number;
  send_end: number;
  current_condition: number | null;
  condition_since_at: string | null;
}

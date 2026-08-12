export interface ConnectionHistoryEvent {
  connected: 0 | 1;
  instant: Date;
  timestamp: string;
}

export interface ConnectionHistory {
  connectedBefore: 0 | 1 | null;
  events: ConnectionHistoryEvent[];
  rangeEnd: Date;
  rangeEndIso: string;
  rangeStart: Date;
  rangeStartIso: string;
  totalPeriods: number;
}

export interface ConnectionSegment {
  connected: 0 | 1;
  end: Date;
  start: Date;
}

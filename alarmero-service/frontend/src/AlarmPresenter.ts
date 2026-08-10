import { UtcMinusThreePresenter, type StatusTone } from "@servicoop/frontend-foundation";

import type { DispatchStatus, IncidentStatus } from "./AlarmModels";

export class AlarmPresenter {
  public constructor(private readonly time = new UtcMinusThreePresenter()) {}

  public statusLabel(status: IncidentStatus): string {
    return { potential: "Potencial", active: "Activa", recovering: "Recuperando", resolved: "Resuelta" }[status];
  }

  public statusTone(status: IncidentStatus): StatusTone {
    return { potential: "warning", active: "danger", recovering: "info", resolved: "success" }[status] as StatusTone;
  }

  public dispatchLabel(status: DispatchStatus | null, notified: number): string {
    if (status === null) {
      return notified === 1 ? "Aceptado" : "No solicitado";
    }
    return {
      pending: "Aceptado / en cola",
      processing: "Enviando por SMTP",
      sent: "Enviado por SMTP",
      failed: "Falló el envío",
    }[status];
  }

  public dispatchTone(status: DispatchStatus | null): StatusTone {
    if (status === "sent") return "success";
    if (status === "failed") return "danger";
    if (status === "pending" || status === "processing") return "warning";
    return "neutral";
  }

  public date(value: string | null): string {
    return this.time.formatInstant(value);
  }

  public age(start: string, end: string | null, referenceNow: string): string {
    return this.time.formatAge(start, end, referenceNow);
  }

  public minutes(value: number | null): string {
    return value === null ? "—" : `${value.toLocaleString("es-AR", { maximumFractionDigits: 1 })} min`;
  }
}

export class OperationalFormatter {
  public percentage(value: unknown, digits = 1): string {
    return typeof value === "number" && Number.isFinite(value)
      ? `${value.toFixed(digits)}%`
      : "N/D";
  }

  public ratioPercentage(value: unknown, digits = 1): string {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0)
      return "N/D";
    const percentage = value <= 1 ? value * 100 : value;
    return `${percentage.toFixed(digits)}%`;
  }

  public bytes(value: unknown): string {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0)
      return "N/D";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let amount = value;
    let unit = 0;
    while (amount >= 1024 && unit < units.length - 1) {
      amount /= 1024;
      unit += 1;
    }
    return unit === 0
      ? `${Math.round(amount)} ${units[unit]}`
      : `${amount.toFixed(1)} ${units[unit]}`;
  }

  public integer(value: unknown): string {
    return typeof value === "number" && Number.isFinite(value)
      ? Math.trunc(value).toLocaleString("es-AR")
      : "N/D";
  }

  public scalar(value: unknown): string {
    if (value === null || value === undefined || value === "") return "N/D";
    if (typeof value === "boolean") return value ? "sí" : "no";
    return String(value);
  }
}

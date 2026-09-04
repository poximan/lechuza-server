export function formatRelayTimestamp(value: string): string {
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) {
    throw new Error(`Estampa MiCOM inválida: ${value}`);
  }
  const day = String(timestamp.getUTCDate()).padStart(2, "0");
  const month = String(timestamp.getUTCMonth() + 1).padStart(2, "0");
  const year = String(timestamp.getUTCFullYear()).slice(-2);
  const hour = String(timestamp.getUTCHours()).padStart(2, "0");
  const minute = String(timestamp.getUTCMinutes()).padStart(2, "0");
  const second = String(timestamp.getUTCSeconds()).padStart(2, "0");
  const millisecond = String(timestamp.getUTCMilliseconds()).padStart(3, "0");
  return `${day}/${month}/${year}, ${hour}:${minute}:${second}.${millisecond}`;
}

export function relayTimestampFormat(value: unknown): string {
  if (value === "private") return "privado";
  if (value === "iec870") return "IEC 870";
  throw new Error(`Formato de estampa MiCOM inválido: ${String(value)}`);
}

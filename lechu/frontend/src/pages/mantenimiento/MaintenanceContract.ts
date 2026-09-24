import { JsonContractReader } from "../../contracts/JsonContractReader";
import type { JsonRecord } from "../../models";

export interface MaintenanceTopology {
  description: string;
  url: string;
}

export interface MaintenancePhone {
  comment: string | null;
  number: string;
}

export interface MaintenancePortMapping {
  external: string | null;
  internal: string;
  localhost: string;
  service: string;
}

export interface MaintenanceContract {
  portMappings: MaintenancePortMapping[];
  phones: {
    estivariz: MaintenancePhone[];
    fontana: MaintenancePhone[];
    general: MaintenancePhone[];
  };
  topology: MaintenanceTopology;
}

export type WakeStatus = "accepted" | "packet_sent" | "ssh_open" | "failed";

export interface WakeOperation {
  broadcastIp: string;
  error: string | null;
  packetBytes: number | null;
  requestId: string;
  source: string;
  startedAt: string;
  status: WakeStatus;
  targetIp: string;
  targetPort: number;
  updatedAt: string;
}

const reader = new JsonContractReader();

function phoneContext(group: string, index?: number, field?: string): string {
  const base = "mantenimiento.telefonos.".concat(group);
  if (index === undefined) return base;
  const item = base.concat("[", String(index), "]");
  return field ? item.concat(".", field) : item;
}

function mappingContext(index: number, field?: string): string {
  const item = "mantenimiento.port_mappings[".concat(String(index), "]");
  return field ? item.concat(".", field) : item;
}

function readPhones(data: JsonRecord, group: string): MaintenancePhone[] {
  return reader.records(data[group], phoneContext(group))
    .map((item, index) => ({
      comment: reader.optionalString(
        item.comentario,
        phoneContext(group, index, "comentario"),
      ),
      number: reader.string(
        item.numero,
        phoneContext(group, index, "numero"),
      ),
    }));
}

export function readMaintenanceContract(data: JsonRecord): MaintenanceContract {
  const topology = reader.record(data.topologia, "mantenimiento.topologia");
  const phones = reader.record(data.telefonos, "mantenimiento.telefonos");
  const portMappings = reader.records(
    data.port_mappings,
    "mantenimiento.port_mappings",
  );
  return {
    topology: {
      description: reader.string(
        topology.descripcion,
        "mantenimiento.topologia.descripcion",
      ),
      url: reader.string(topology.url, "mantenimiento.topologia.url"),
    },
    phones: {
      estivariz: readPhones(phones, "estivariz"),
      fontana: readPhones(phones, "fontana"),
      general: readPhones(phones, "general"),
    },
    portMappings: portMappings.map((item, index) => ({
      external: reader.optionalString(
        item.externo,
        mappingContext(index, "externo"),
      ),
      internal: reader.string(
        item.interno,
        mappingContext(index, "interno"),
      ),
      localhost: reader.string(
        item.localhost,
        mappingContext(index, "localhost"),
      ),
      service: reader.string(
        item.servicio,
        mappingContext(index, "servicio"),
      ),
    })),
  };
}

export function readWakeOperation(data: JsonRecord): WakeOperation {
  const context = "mantenimiento.wol";
  const contractVersion = reader.number(
    data.contract_version,
    `${context}.contract_version`,
  );
  if (contractVersion !== 1) {
    throw new Error(`Contrato inválido: ${context}.contract_version desconocida`);
  }
  const status = reader.string(data.status, `${context}.status`);
  if (!["accepted", "packet_sent", "ssh_open", "failed"].includes(status)) {
    throw new Error(`Contrato inválido: ${context}.status desconocido`);
  }
  return {
    broadcastIp: reader.string(data.broadcast_ip, `${context}.broadcast_ip`),
    error: reader.optionalString(data.error, `${context}.error`),
    packetBytes: reader.optionalNumber(
      data.packet_bytes,
      `${context}.packet_bytes`,
    ),
    requestId: reader.string(data.request_id, `${context}.request_id`),
    source: reader.string(data.source, `${context}.source`),
    startedAt: reader.string(data.started_at, `${context}.started_at`),
    status: status as WakeStatus,
    targetIp: reader.string(data.target_ip, `${context}.target_ip`),
    targetPort: reader.number(data.target_port, `${context}.target_port`),
    updatedAt: reader.string(data.updated_at, `${context}.updated_at`),
  };
}

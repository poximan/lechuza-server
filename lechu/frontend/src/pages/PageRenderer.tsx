import type { LechuApiClient } from "../LechuApiClient";
import { ExemysPage } from "./ExemysPage";
import type { JsonRecord } from "../models";
import { BrokerPage } from "./BrokerPage";
import { CharitoPage } from "./CharitoPage";
import { EmailPage } from "./EmailPage";
import { GeneratorsPage } from "./GeneratorsPage";
import { MaintenancePage } from "./mantenimiento/MaintenancePage";
import { MensageloPage } from "./MensageloPage";
import { ProxmoxPage } from "./ProxmoxPage";
import { RelaysPage } from "./RelaysPage";

export interface PageRendererProps {
  client: LechuApiClient;
  data: JsonRecord;
  onChanged: () => Promise<void>;
  onAttentionChange: (active: boolean) => void;
  page: string;
  protectedMode: boolean;
}

export function PageRenderer({
  client,
  data,
  onChanged,
  onAttentionChange,
  page,
  protectedMode,
}: PageRendererProps) {
  switch (page) {
    case "exemys":
      return <ExemysPage client={client} data={data} />;
    case "charito":
      return <CharitoPage data={data} />;
    case "generadores":
      return (
        <GeneratorsPage data={data} onAttentionChange={onAttentionChange} />
      );
    case "proxmox":
      return <ProxmoxPage client={client} data={data} onChanged={onChanged} />;
    case "reles":
      return (
        <RelaysPage
          client={client}
          data={data}
          onChanged={onChanged}
          protectedMode={protectedMode}
        />
      );
    case "mantenimiento":
      return <MaintenancePage data={data} />;
    case "mensagelo":
      return <MensageloPage data={data} />;
    case "broker":
      return <BrokerPage client={client} data={data} onChanged={onChanged} />;
    case "email":
      return (
        <EmailPage client={client} data={data} protectedMode={protectedMode} />
      );
    default:
      throw new Error(`Página Lechu desconocida: ${page}`);
  }
}

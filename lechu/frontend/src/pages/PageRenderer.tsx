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
import { NetworkAnalyzersPage } from "./NetworkAnalyzersPage";
import { FlowMetersPage } from "./caudalimetros/FlowMetersPage";

export interface PageRendererProps {
  client: LechuApiClient;
  data: JsonRecord;
  onChanged: () => Promise<void>;
  page: string;
  protectedMode: boolean;
}

export function PageRenderer({
  client,
  data,
  onChanged,
  page,
  protectedMode,
}: PageRendererProps) {
  switch (page) {
    case "caudalimetros":
      return <FlowMetersPage client={client} data={data} onChanged={onChanged} />;
    case "exemys":
      return <ExemysPage client={client} data={data} />;
    case "charito":
      return <CharitoPage data={data} />;
    case "generadores":
      return <GeneratorsPage data={data} />;
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
    case "analizadores":
      return (
        <NetworkAnalyzersPage
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

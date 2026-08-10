import type { PanelexemysApiClient } from "../PanelexemysApiClient";
import { OverviewPage } from "../components/OverviewPage";
import type { JsonRecord } from "../models";
import { BrokerPage } from "./BrokerPage";
import { CharitoPage } from "./CharitoPage";
import { EmailPage } from "./EmailPage";
import { GeneratorsPage } from "./GeneratorsPage";
import { MaintenancePage } from "./MaintenancePage";
import { MensageloPage } from "./MensageloPage";
import { ProxmoxPage } from "./ProxmoxPage";
import { RelaysPage } from "./RelaysPage";

export interface PageRendererProps {
  client: PanelexemysApiClient;
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
    case "overview":
      return <OverviewPage client={client} data={data} />;
    case "charito":
      return <CharitoPage data={data} />;
    case "generadores":
      return <GeneratorsPage data={data} />;
    case "proxmox":
      return <ProxmoxPage client={client} data={data} onChanged={onChanged} />;
    case "reles":
      return <RelaysPage client={client} data={data} onChanged={onChanged} />;
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
      throw new Error(`Página Panelexemys desconocida: ${page}`);
  }
}

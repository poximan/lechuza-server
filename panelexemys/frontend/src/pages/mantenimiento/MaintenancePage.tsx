import { Card } from "@servicoop/frontend-foundation";

import type { JsonRecord } from "../../models";
import commonStyles from "../Pages.module.css";
import {
  readMaintenanceContract,
  type MaintenancePhone,
  type MaintenancePortMapping,
  type MaintenanceTopology,
} from "./MaintenanceContract";
import styles from "./MaintenancePage.module.css";

function TopologyImage({ topology }: { topology: MaintenanceTopology }) {
  return (
    <a
      className={styles.topologyLink}
      href={topology.url}
      rel="noreferrer"
      target="_blank"
      title="Abrir topología en tamaño completo"
    >
      <img
        alt={topology.description}
        className={styles.topologyImage}
        src={topology.url}
      />
    </a>
  );
}

function PhoneColumn({ title, items }: { title: string; items: MaintenancePhone[] }) {
  return (
    <Card>
      <h3>{title}</h3>
      <ul className={styles.phoneList}>
        {items.map((item, index) => (
          <li key={[item.number, index].join("-")}>
            <strong>{item.number}</strong>
            {item.comment ? (
              <span className={commonStyles.muted}> ({item.comment})</span>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function PortMappings({ items }: { items: MaintenancePortMapping[] }) {
  return (
    <Card>
      <div className={commonStyles.cardHeader}>
        <h2>Mapeo de puertos (docker &lt;-&gt; localhost &lt;-&gt; https)</h2>
      </div>
      <div className={commonStyles.tableWrap}>
        <table className={commonStyles.table}>
          <thead>
            <tr>
              <th>Servicio</th>
              <th>Docker interno</th>
              <th>HTTPS público</th>
              <th>Localhost pruebas</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <tr key={[item.service, index].join("-")}>
                <td>{item.service}</td>
                <td><code>{item.internal}</code></td>
                <td><code>{item.external}</code></td>
                <td><code>{item.localhost}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function MaintenancePage({ data }: { data: JsonRecord }) {
  const contract = readMaintenanceContract(data);
  return (
    <div className={commonStyles.stack}>
      <Card>
        <div className={commonStyles.cardHeader}>
          <div>
            <h2>Topología de red</h2>
            <p className={commonStyles.muted}>
              Seleccione la imagen para verla en tamaño completo.
            </p>
          </div>
        </div>
        <div className={styles.topologyViewport}>
          <TopologyImage topology={contract.topology} />
        </div>
      </Card>
      <section className={commonStyles.stack}>
        <h2 className={commonStyles.sectionTitle}>Líneas telefónicas</h2>
        <div className={styles.phoneGrid}>
          <PhoneColumn items={contract.phones.fontana} title="Fontana" />
          <PhoneColumn items={contract.phones.estivariz} title="Estivariz" />
        </div>
        <div className={styles.phoneGeneral}>
          <PhoneColumn items={contract.phones.general} title="General" />
        </div>
      </section>
      <PortMappings items={contract.portMappings} />
    </div>
  );
}

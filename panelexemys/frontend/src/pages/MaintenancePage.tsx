import { Card } from "@servicoop/frontend-foundation";

import { JsonContractReader } from "../contracts/JsonContractReader";
import { OperationalFormatter } from "../contracts/OperationalFormatter";
import type { JsonRecord } from "../models";
import styles from "./Pages.module.css";

const reader = new JsonContractReader();
const formatter = new OperationalFormatter();

function TopologyDiagram({ services }: { services: JsonRecord[] }) {
  const height = Math.max(360, services.length * 74 + 80);
  return (
    <svg
      aria-label="Topología HTTP de la plataforma"
      className={styles.diagram}
      role="img"
      viewBox={`0 0 900 ${height}`}
    >
      <rect
        className={styles.diagramNode}
        height="70"
        rx="12"
        width="180"
        x="30"
        y={height / 2 - 35}
      />
      <text
        fontSize="18"
        fontWeight="800"
        textAnchor="middle"
        x="120"
        y={height / 2 - 5}
      >
        Cliente HTTPS
      </text>
      <text fontSize="13" textAnchor="middle" x="120" y={height / 2 + 18}>
        comunicaciones.servicoop.com.ar
      </text>
      <line
        className={styles.diagramWire}
        x1="210"
        x2="330"
        y1={height / 2}
        y2={height / 2}
      />
      <rect
        className={styles.diagramNode}
        height="86"
        rx="12"
        width="190"
        x="330"
        y={height / 2 - 43}
      />
      <text
        fontSize="20"
        fontWeight="800"
        textAnchor="middle"
        x="425"
        y={height / 2 - 6}
      >
        edge-gateway
      </text>
      <text fontSize="14" textAnchor="middle" x="425" y={height / 2 + 20}>
        proxy HTTP único
      </text>
      {services.map((service, index) => {
        const y = 45 + index * 74;
        return (
          <g key={String(service.servicio ?? index)}>
            <path
              className={styles.diagramWire}
              d={`M520 ${height / 2} H590 V${y + 28} H640`}
            />
            <rect
              className={styles.diagramNode}
              height="56"
              rx="10"
              width="225"
              x="640"
              y={y}
            />
            <text
              fontSize="16"
              fontWeight="800"
              textAnchor="middle"
              x="752"
              y={y + 23}
            >
              {formatter.scalar(service.servicio)}
            </text>
            <text fontSize="12" textAnchor="middle" x="752" y={y + 43}>
              {formatter.scalar(service.interno)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function PhoneColumn({ title, items }: { title: string; items: JsonRecord[] }) {
  return (
    <Card>
      <h3>{title}</h3>
      <ul className={styles.phoneList}>
        {items.map((item, index) => (
          <li key={`${String(item.numero)}-${index}`}>
            <strong>{formatter.scalar(item.numero)}</strong>
            {item.comentario ? (
              <span className={styles.muted}>
                {" "}
                ({formatter.scalar(item.comentario)})
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function MaintenancePage({ data }: { data: JsonRecord }) {
  const phones = reader.record(data.telefonos, "mantenimiento.telefonos");
  const mappings = reader.records(
    data.port_mappings,
    "mantenimiento.port_mappings",
  );
  return (
    <div className={styles.stack}>
      <Card>
        <div className={styles.cardHeader}>
          <h2>Topología de red</h2>
        </div>
        <div className={styles.topologyViewport}>
          <TopologyDiagram services={mappings} />
        </div>
      </Card>
      <section className={styles.stack}>
        <h2 className={styles.sectionTitle}>Líneas telefónicas</h2>
        <div className={styles.phoneGrid}>
          <PhoneColumn
            items={reader.records(
              phones.fontana,
              "mantenimiento.telefonos.fontana",
            )}
            title="Fontana"
          />
          <PhoneColumn
            items={reader.records(
              phones.estivariz,
              "mantenimiento.telefonos.estivariz",
            )}
            title="Estivariz"
          />
        </div>
        <div className={styles.phoneGeneral}>
          <PhoneColumn
            items={reader.records(
              phones.general,
              "mantenimiento.telefonos.general",
            )}
            title="General"
          />
        </div>
      </section>
      <Card>
        <div className={styles.cardHeader}>
          <h2>Mapeo de puertos (docker &lt;-&gt; localhost &lt;-&gt; https)</h2>
        </div>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Servicio</th>
                <th>Docker interno</th>
                <th>HTTPS público</th>
                <th>Localhost pruebas</th>
              </tr>
            </thead>
            <tbody>
              {mappings.map((item, index) => (
                <tr key={`${String(item.servicio)}-${index}`}>
                  <td>{formatter.scalar(item.servicio)}</td>
                  <td>
                    <code>{formatter.scalar(item.interno)}</code>
                  </td>
                  <td>
                    <code>{formatter.scalar(item.externo)}</code>
                  </td>
                  <td>
                    <code>{formatter.scalar(item.localhost)}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

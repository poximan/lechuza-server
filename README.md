# lechuza-server

Mono-repo de la plataforma Lechuza orientada a microservicios. Este arbol concentra el backend operativo, la capa web interna, los adaptadores de integracion y los recursos compartidos que se despliegan juntos desde `docker-compose.yml`.

La puerta publica HTTP/HTTPS ya no vive en este repo. Esa responsabilidad fue migrada a `edge-platform`, que publica `comunicaciones.servicoop.com.ar`, aplica TLS, muestra el menu de bienvenida y enruta hacia los servicios internos por la red Docker externa `servicoop-edge-net`.

La arquitectura sigue una separacion estricta de incumbencias:

- `panelexemys` es la interfaz operativa y el orquestador de visualizacion, alarmas y mensajeria.
- `mensagelo` encapsula el envio de correo y su persistencia operacional.
- `modbus-collector-service` consulta el dominio Modbus/GRD y expone estado por HTTP y MQTT.
- `pve-service` adapta Proxmox VE al resto del sistema.
- `modem-link-monitor` monitorea conectividad del modem/router y publica su estado.
- `charito-service` releva instancias remotas de `charo-daemon` sin mezclar su dominio con el resto del sistema.
- `scada-citec-service` adapta un daemon SCADA externo para la vista mimic.
- `shared` concentra utilidades y paquetes compartidos.
- `volumes` aloja el estado persistente de runtime de los contenedores.

Quedan explicitamente fuera de alcance de este mono-repo:

- La publicacion HTTP/HTTPS, que corresponde a `edge-platform`.
- `panelito`, que actua como consumidor externo de contratos MQTT/HTTP.
- `charo-daemon`, que sigue siendo una dependencia externa relevada por `charito-service` y `scada-citec-service`.

## Mapa funcional

| Directorio | Rol principal | Interfaces |
| --- | --- | --- |
| `panelexemys` | Dashboard, alarmas y coordinacion | HTTP interno, MQTT |
| `mensagelo` | API de email y cola de envio | HTTP interno |
| `modbus-collector-service` | Estado GRD/MiCOM y observacion Modbus | HTTP interno, MQTT |
| `pve-service` | Estado e historial de Proxmox | HTTP interno, MQTT |
| `modem-link-monitor` | Sondeo del enlace de modem/router | HTTP interno, MQTT |
| `charito-service` | Relevamiento de instancias remotas | HTTP interno, MQTT |
| `scada-citec-service` | Adaptador mimic sobre daemon SCADA externo | HTTP interno |
| `shared` | Codigo compartido | Importado por servicios Python |
| `volumes` | Datos persistidos en runtime | Volumenes Docker |

## Integracion prevista

`docker-compose.yml` define el despliegue conjunto y deja clara la frontera entre servicios:

- `panelexemys`, `modbus-collector-service`, `pve-service`, `modem-link-monitor` y `scada-citec-service` se conectan tambien a `servicoop-edge-net` para ser alcanzados exclusivamente por `edge-gateway`.
- `panelexemys` consume por HTTP a `mensagelo`, `modbus-collector-service`, `pve-service`, `modem-link-monitor` y `charito-service`.
- `modbus-collector-service`, `pve-service` y `modem-link-monitor` publican estados operativos en MQTT.
- `charito-service` consulta endpoints remotos `/metrics` declarados en `CHARITO_TARGETS_JSON` y publica el estado consolidado en MQTT como fuente de verdad para `panelito`; la identidad estable de cada daemon se declara explicitamente como `id`.
- `scada-citec-service` consulta un daemon externo definido por `SCADA_DAEMON_BASE_URL`.

La red externa no la crea este compose. Debe existir antes del despliegue porque esta declarada como `external: true`:

```powershell
docker network create servicoop-edge-net
```

Ese comando se ejecuta una sola vez en el host Docker. Si la red ya existe, no hay que repetirlo.

La persistencia operativa vive en `volumes/`. Los consumidores deben usar los contratos HTTP/MQTT declarados por cada servicio y no acceder en forma directa a las bases o archivos internos de otro modulo.

## Estructura del mono-repo

```text
lechuza-server/
|- docker-compose.yml
|- .env
|- .env.example
|- .gitignore
|- panelexemys/
|- mensagelo/
|- modbus-collector-service/
|- pve-service/
|- modem-link-monitor/
|- charito-service/
|- scada-citec-service/
|- shared/
`- volumes/
```

## Convenciones del repo

- Existe un unico repositorio Git en la raiz de `lechuza-server`.
- Los repositorios anidados y archivos Git auxiliares de subdirectorios fueron eliminados para evitar acoplamientos y estados inconsistentes.
- El `.gitignore` raiz concentra las reglas de artefactos Python, secretos locales y datos de runtime.
- `docker-compose.yml` toma secretos, usuarios, claves y endpoints reales desde `.env`; el repo solo publica la plantilla segura en `.env.example`.
- Cada microservicio mantiene su propio `README.md` cuando necesita documentar contratos, endpoints o configuracion especifica.

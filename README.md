# lechuza-server

Mono-repo de la plataforma Lechuza orientada a microservicios. Este arbol concentra el backend operativo, la capa web interna, los adaptadores de integracion y los recursos compartidos que se despliegan juntos desde `docker-compose.yml`.

La arquitectura sigue una separacion estricta de incumbencias:

- `login-service` es la puerta de entrada HTTP/HTTPS y protege el acceso a los servicios internos.
- `panelexemys` es la interfaz operativa y el orquestador de visualizacion, alarmas y mensajeria.
- `mensagelo` encapsula el envio de correo y su persistencia operacional.
- `modbus-mw-service` consulta el dominio Modbus/GRD y expone estado por HTTP y MQTT.
- `pve-service` adapta Proxmox VE al resto del sistema.
- `router-telef-service` monitorea conectividad del modem/router y publica su estado.
- `charito-service` releva instancias remotas de `charo-daemon` sin mezclar su dominio con el resto del sistema.
- `scada-citec-service` adapta un daemon SCADA externo para la vista mimic.
- `shared` concentra utilidades y paquetes compartidos.
- `volumes` aloja el estado persistente de runtime de los contenedores.

Quedan explicitamente fuera de alcance de este mono-repo:

- `panelito`, que actua como consumidor externo de contratos MQTT/HTTP.
- `charo-daemon`, que sigue siendo una dependencia externa relevada por `charito-service` y `scada-citec-service`.

## Mapa funcional

| Directorio | Rol principal | Interfaces |
| --- | --- | --- |
| `login-service` | Proxy inverso y login | HTTP/HTTPS publico |
| `panelexemys` | Dashboard, alarmas y coordinacion | HTTP interno, MQTT |
| `mensagelo` | API de email y cola de envio | HTTP interno |
| `modbus-mw-service` | Estado GRD/MiCOM y observacion Modbus | HTTP interno, MQTT |
| `pve-service` | Estado e historial de Proxmox | HTTP interno, MQTT |
| `router-telef-service` | Sondeo del enlace de modem/router | HTTP interno, MQTT |
| `charito-service` | Relevamiento de instancias remotas | HTTP interno |
| `scada-citec-service` | Adaptador mimic sobre daemon SCADA externo | HTTP interno |
| `shared` | Codigo compartido | Importado por servicios Python |
| `volumes` | Datos persistidos en runtime | Volumenes Docker |

## Integracion prevista

`docker-compose.yml` define el despliegue conjunto y deja clara la frontera entre servicios:

- `login-service` expone la entrada publica y enruta a `panelexemys`, `modbus-mw-service`, `pve-service`, `router-telef-service` y `scada-citec-service`.
- `panelexemys` consume por HTTP a `mensagelo`, `modbus-mw-service`, `pve-service`, `router-telef-service` y `charito-service`.
- `modbus-mw-service`, `pve-service` y `router-telef-service` publican estados operativos en MQTT.
- `charito-service` consulta endpoints remotos `/metrics` y `/identity` declarados en `CHARITO_TARGETS_JSON`.
- `scada-citec-service` consulta un daemon externo definido por `SCADA_DAEMON_BASE_URL`.

La persistencia operativa vive en `volumes/`. Los consumidores deben usar los contratos HTTP/MQTT declarados por cada servicio y no acceder en forma directa a las bases o archivos internos de otro modulo.

## Estructura del mono-repo

```text
lechuza-server/
|- docker-compose.yml
|- .env
|- .env.example
|- .gitignore
|- login-service/
|- panelexemys/
|- mensagelo/
|- modbus-mw-service/
|- pve-service/
|- router-telef-service/
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

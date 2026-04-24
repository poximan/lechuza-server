# login-service

Proxy inverso NGINX+login estático que protege todos los servicios internos.

- Redirige HTTP→HTTPS y sirve la pantalla de login (`/usr/share/nginx/html`).
- Entrega cookies `panelexemys_mode` para modo seguro/protegido.
- Encapsula Panelexemys (`/dash/`), Modbus (`/api/`), PVE (`/pve/`), router (`/router/`) y Scada (`/scada/`).
- Directivas HSTS/CSP/XFO refuerzan la exposición pública.

La configuracion sensible no se versiona:

- El usuario y password de modo protegido salen de `.env`.
- Los upstreams auxiliares se renderizan desde variables de entorno al iniciar el contenedor.
- El repo publica la plantilla `\.env.example`, mientras que los valores reales viven en `\.env`.

Los certificados TLS autofirmados se generan en build y el servicio no usa volumen propio en el `docker-compose` actual.




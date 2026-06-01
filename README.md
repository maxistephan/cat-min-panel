# `Cat-min Control Panel`

> A lightweight self-hosted web panel for managing a Minecraft server running in Docker.
> Built with Flask, plain HTML/CSS/JS, and a Sanrio-inspired aesthetic.

## Features

- Live server status (running / exited / failed) with animated pulse indicator
- Player count via RCON
- Scheduled restart: 5-minute countdown with in-game notifications
- Instant restart: saves the world and reboots immediately
- RCON command console with live output
- Live container log streaming
- Simple Token-gated login screen

## Stack

- **Backend**: Python 3.12, Flask, python-rcon, docker-py
- **Frontend**: Vanilla HTML, CSS, JS
- **Fonts**: M PLUS Rounded 1c, Zen Maru Gothic
- **Tested Proxies**: Traefik

## Setup

### Docker Compose

```yaml
services:
  ################
  # CATmin Panel #
  ################
  mc-panel:
    image: ghcr.io/maxistephan/cat-min-panel:latest
    container_name: catmin-panel
    restart: on-failure:10
    ports:
      - 5000:5000/tcp
    environment:
      - TZ=Europe/Berlin
      - PANEL_TOKEN_FILE=/run/secrets/panel_token
      - MC_SERVICE=mc-server.service
      - RCON_PASSWORD_FILE=/run/secrets/rcon_password
      - RCON_HOST=0.0.0.0
      - RCON_PORT=25575
      - MC_CONTAINER=minecraft-server  # in case you named your docker container "minecraft-server"
    secrets:
      - panel_token
      - rcon_password
    volumes:
      # Needed so the panel can call systemctl on the host
      - /run/systemd/private:/run/systemd/private:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /var/run/dbus/system_bus_socket:/var/run/dbus/system_bus_socket
      - ./app/:/app
    # Run as root so sudo systemctl works; lock down with PANEL_TOKEN instead
    privileged: true

secrets:
  panel_token:
    file: ./secrets/panel_token
  rcon_password:
    file: ./secrets/rcon_password
```

### Local Setup

#### 1. Create secret files

```bash
mkdir -p secrets
echo "yourStrongTokenHere" > secrets/panel_token
echo "yourRconPassword"    > secrets/rcon_password
chmod 600 secrets/*
```

#### 2. Add to your compose file

| Variable        | Description                                      |
|-----------------|--------------------------------------------------|
| `MC_CONTAINER`  | Name of your Minecraft container                 |
| `RCON_HOST`     | Hostname/service name of your Minecraft container|
| `RCON_PORT`     | RCON port (default: `25575`)                     |
| `PANEL_TOKEN_FILE`   | Path to the token secret (default shown)    |
| `RCON_PASSWORD_FILE` | Path to the RCON secret (default shown)     |

Secrets can also be supplied directly as env vars without `_FILE`:

```yaml
environment:
  - PANEL_TOKEN=yourTokenHere
  - RCON_PASSWORD=yourRconPassword
```

#### 3. Build and run

```bash
docker compose build mc-panel
docker compose up -d mc-panel
```

## API Endpoints

| Method | Path                  | Auth       | Description                        |
|--------|-----------------------|------------|------------------------------------|
| `GET`  | `/`                   | -          | Serves the panel UI                |
| `GET`  | `/resources/<file>`   | -          | Serves static assets (CSS, JS)     |
| `GET`  | `/api/status`         | Bearer token | Server status, player count, restart log |
| `POST` | `/api/restart`        | Bearer token | Initiate 5-minute scheduled restart |
| `POST` | `/api/restart-now`    | Bearer token | Immediate restart (save + reboot)  |
| `POST` | `/api/command`        | Bearer token | Send an RCON command               |
| `GET`  | `/api/logs/stream`    | `?token=`  | Live container log stream (SSE)    |

## License

GNU General Public License v2.0. See [LICENSE](LICENSE).  


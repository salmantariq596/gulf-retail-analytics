# Lightdash CLI for publishing dashboards (`lightdash upload` needs Node 24+).
# Built by publish.ps1:  docker build -f bi/lightdash/cli.Dockerfile -t najm-lightdash-cli:3.392.0 bi/lightdash
FROM node:24.11.1-bookworm-slim
RUN npm install --global --no-audit --no-fund @lightdash/cli@3.392.0 && npm cache clean --force
ENTRYPOINT ["lightdash"]

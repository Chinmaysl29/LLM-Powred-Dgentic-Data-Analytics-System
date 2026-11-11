FROM node:22-bookworm-slim AS node
FROM dataanalyst-backend:latest
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
COPY backend/dev-requirements.txt /tmp/dev-requirements.txt
RUN pip install --no-cache-dir -r /tmp/dev-requirements.txt && pip check
WORKDIR /workspace
HEALTHCHECK NONE
CMD ["sleep", "infinity"]

# CLI version and npm package are explicit build arguments supplied by the launcher.
FROM node:22.19.0-bookworm-slim AS cli
ARG NPM_PACKAGE
ARG CLI_VERSION
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 make g++ git ca-certificates patchelf \
    && rm -rf /var/lib/apt/lists/*
RUN test -n "$NPM_PACKAGE" && test -n "$CLI_VERSION" \
    && npm install --global --prefix /opt/sle/native-runtime \
      "$NPM_PACKAGE@$CLI_VERSION" \
    && cp /usr/local/bin/node /opt/sle/native-runtime/bin/node \
    && mkdir -p /opt/sle/native-runtime/lib/runtime \
    && cp -L "$(g++ -print-file-name=libstdc++.so.6)" /opt/sle/native-runtime/lib/runtime/ \
    && cp -L "$(gcc -print-file-name=libgcc_s.so.1)" /opt/sle/native-runtime/lib/runtime/ \
    && patchelf --set-rpath '$ORIGIN/../lib/runtime' /opt/sle/native-runtime/bin/node \
    && printf '%s\n' 'export PATH="/opt/sle/native-runtime/bin:$PATH"' \
      > /opt/sle/native-runtime/nvm.sh

FROM sle-gui-mcp:1.0.1
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir 'PyYAML==6.0.2'
COPY --from=cli /opt/sle/native-runtime /opt/sle/native-runtime
COPY sle/ /opt/sle/sle/
ENV PATH="/opt/sle/native-runtime/bin:$PATH" PYTHONPATH=/opt/sle
WORKDIR /app
ENTRYPOINT []
CMD ["sleep", "infinity"]

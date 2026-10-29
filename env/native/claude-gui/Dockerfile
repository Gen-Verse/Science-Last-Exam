# Build context is prepared by scripts/run_claude_gui.py from pinned local assets.
FROM sle-gui-mcp:1.0.1
COPY claude /usr/local/bin/claude
COPY gui_mcp_client.py /opt/sle/sle/gui_mcp_client.py
RUN chmod 755 /usr/local/bin/claude && /usr/local/bin/claude --version
ENV PYTHONPATH=/opt/sle
WORKDIR /app
ENTRYPOINT []
CMD ["sleep", "infinity"]

FROM sle-thrombosis-science:0.1.1
USER root
COPY . /tests/
RUN chmod -R a+rX /tests && chmod +x /tests/test.sh && \
    /opt/venv/bin/python -m pytest -q /tests/test_contract.py
WORKDIR /tests

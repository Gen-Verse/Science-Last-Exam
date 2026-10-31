FROM python:3.12.1-slim-bookworm
COPY . /tests
RUN mkdir -p /submission /logs/verifier && chmod +x /tests/test.sh
CMD ["sleep", "infinity"]

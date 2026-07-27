FROM python:3.13-slim

RUN pip install --no-cache-dir pandas numpy scipy
COPY runner.py /opt/runner.py
USER 65534:65534
ENTRYPOINT ["python", "/opt/runner.py"]

FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "requests==2.32.3"

COPY provision.py dashboard_vehicle_tracking.json ./

RUN useradd --system --create-home boxtech && chown -R boxtech:boxtech /app
USER boxtech

ENTRYPOINT ["python", "-u", "provision.py"]

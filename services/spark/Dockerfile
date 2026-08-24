FROM spark:python3-java17

USER root

# Install required Python deps (DO NOT reinstall pyspark)
RUN pip install --no-cache-dir \
    delta-spark==3.2.1 \
    pyiceberg==0.8.1 \
    boto3==1.37.24 \
    opentelemetry-api==1.31.1 \
    opentelemetry-sdk==1.31.1 \
    opentelemetry-exporter-otlp==1.31.1

WORKDIR /app
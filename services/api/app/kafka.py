import json
from confluent_kafka import Producer

from app.config import settings

producer = Producer({"bootstrap.servers": settings.redpanda_brokers, "client.id": "assessment-api"})


def publish(topic: str, key: str, value: dict):
    producer.produce(topic=topic, key=key.encode("utf-8"), value=json.dumps(value).encode("utf-8"))
    producer.flush(5)

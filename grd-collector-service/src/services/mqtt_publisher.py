from logosaurio import Logosaurio
from mqtt_json_publisher import MqttJsonPublisher

from src import config


class GrdMqttPublisher(MqttJsonPublisher):
    def __init__(self, logger: Logosaurio) -> None:
        super().__init__(
            logger,
            host=config.MQTT_BROKER_HOST,
            port=config.MQTT_BROKER_PORT,
            username=config.MQTT_BROKER_USERNAME,
            password=config.MQTT_BROKER_PASSWORD,
            keepalive=config.MQTT_KEEPALIVE,
            reconnect_delay_min=config.MQTT_RECONNECT_DELAY_MIN,
            reconnect_delay_max=config.MQTT_RECONNECT_DELAY_MAX,
            publish_timeout_seconds=config.MQTT_PUBLISH_TIMEOUT_SECONDS,
            use_tls=config.MQTT_BROKER_USE_TLS,
            tls_insecure=config.MQTT_TLS_INSECURE,
        )

    def publish_grado(self, payload: dict) -> bool:
        return self.publish_json(
            config.MQTT_TOPIC_GRADO,
            payload,
            config.MQTT_PUBLISH_QOS_STATE,
            config.MQTT_PUBLISH_RETAIN_STATE,
        )

    def publish_grds(self, payload: dict) -> bool:
        return self.publish_json(
            config.MQTT_TOPIC_GRDS,
            payload,
            config.MQTT_PUBLISH_QOS_STATE,
            config.MQTT_PUBLISH_RETAIN_STATE,
        )

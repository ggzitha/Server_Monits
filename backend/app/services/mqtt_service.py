import asyncio
import logging
import ssl
import time
from typing import Optional, Dict, Any, Callable
import paho.mqtt.client as mqtt

from backend.app.core.config import settings
from backend.app.core.security import decrypt_secret, encrypt_secret

logger = logging.getLogger("server_monits.mqtt")


class MQTTService:
    """Manages connection to the external Mosquitto MQTT broker with backoff and status."""

    def __init__(self):
        self.client: Optional[mqtt.Client] = None
        self.is_connected: bool = False
        self.last_seen_message_at: Optional[float] = None
        self.connection_status: str = "disconnected"  # "connected", "connecting", "disconnected", "error"
        self.last_error: Optional[str] = None
        self.reconnect_delay: float = 2.0
        self.max_reconnect_delay: float = 60.0
        self.config: Dict[str, Any] = {}
        self._loop_task: Optional[asyncio.Task] = None
        self._message_callbacks: list[Callable[[str, bytes], None]] = []

    def set_config(
        self,
        host: str,
        port: int = 1883,
        username: Optional[str] = None,
        password_encrypted: Optional[str] = None,
        tls_enabled: bool = False,
        ca_cert: Optional[str] = None,
        client_id: Optional[str] = None,
    ):
        """Set connection parameters."""
        self.config = {
            "host": host.strip() if host else "",
            "port": int(port),
            "username": username.strip() if username else "",
            "password_encrypted": password_encrypted or "",
            "tls_enabled": bool(tls_enabled),
            "ca_cert": ca_cert or "",
            "client_id": client_id or f"monits_{int(time.time())}",
        }

    def register_callback(self, cb: Callable[[str, bytes], None]):
        """Register a callback for incoming messages."""
        if cb not in self._message_callbacks:
            self._message_callbacks.append(cb)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.is_connected = True
            self.connection_status = "connected"
            self.last_error = None
            self.reconnect_delay = 2.0
            logger.info("Successfully connected to external Mosquitto MQTT broker.")
        else:
            self.is_connected = False
            self.connection_status = "error"
            self.last_error = f"Connect failed with code {rc}"
            logger.warning(f"MQTT connect failed: rc={rc}")

    def _on_disconnect(self, client, userdata, rc, properties=None):
        self.is_connected = False
        self.connection_status = "disconnected"
        if rc != 0:
            self.last_error = f"Unexpected disconnection (rc={rc})"
            logger.warning(f"MQTT disconnected unexpectedly (rc={rc}). Will reconnect with backoff.")

    def _on_message(self, client, userdata, msg):
        self.last_seen_message_at = time.time()
        for cb in self._message_callbacks:
            try:
                cb(msg.topic, msg.payload)
            except Exception as e:
                logger.error(f"Error in MQTT message callback: {e}")

    async def start(self):
        """Start the background connection worker."""
        if not self.config.get("host"):
            # Check settings defaults
            if settings.MQTT_HOST:
                self.set_config(
                    host=settings.MQTT_HOST,
                    port=settings.MQTT_PORT,
                    username=settings.MQTT_USERNAME,
                    password_encrypted=encrypt_secret(settings.MQTT_PASSWORD) if settings.MQTT_PASSWORD else None,
                    tls_enabled=settings.MQTT_TLS,
                    client_id=settings.MQTT_CLIENT_ID,
                )
            else:
                self.connection_status = "not_configured"
                return

        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        """Background loop handling connection and exponential backoff."""
        while True:
            host = self.config.get("host")
            if not host:
                self.connection_status = "not_configured"
                await asyncio.sleep(10)
                continue

            try:
                if not self.is_connected:
                    self.connection_status = "connecting"
                    self._init_and_connect_sync()

                await asyncio.sleep(5)
            except Exception as e:
                self.is_connected = False
                self.connection_status = "error"
                self.last_error = str(e)
                logger.warning(f"MQTT connection attempt failed: {e}. Retrying in {self.reconnect_delay:.1f}s")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 1.5, self.max_reconnect_delay)

    def _init_and_connect_sync(self):
        """Synchronous connection setup."""
        host = self.config["host"]
        port = self.config["port"]
        client_id = self.config.get("client_id") or f"monits_{int(time.time())}"

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

        # Credentials
        username = self.config.get("username")
        enc_pass = self.config.get("password_encrypted")
        password = decrypt_secret(enc_pass) if enc_pass else None
        if username:
            client.username_pw_set(username, password)

        # TLS
        if self.config.get("tls_enabled"):
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED if self.config.get("ca_cert") else ssl.CERT_NONE)

        client.connect(host, port, keepalive=60)
        client.loop_start()
        self.client = client

    async def test_connection(self, host: str, port: int, username: str, password: str, tls: bool, topic: str, timeout: float = 6.0) -> Dict[str, Any]:
        """Test connection to an MQTT broker and subscribe to test topic, waiting for sample message."""
        loop = asyncio.get_running_loop()
        sample_received = None
        connect_rc = None
        error_msg = None

        def run_test():
            nonlocal sample_received, connect_rc, error_msg
            test_client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"test_monits_{int(time.time())}",
            )
            connected_event = asyncio.Event()

            def on_c(c, userdata, flags, rc, props=None):
                nonlocal connect_rc
                connect_rc = rc
                if rc == 0:
                    c.subscribe(topic)

            def on_m(c, userdata, msg):
                nonlocal sample_received
                sample_received = {
                    "topic": msg.topic,
                    "payload": msg.payload.decode("utf-8", errors="replace"),
                }

            test_client.on_connect = on_c
            test_client.on_message = on_m

            if username:
                test_client.username_pw_set(username, password)

            if tls:
                test_client.tls_set(cert_reqs=ssl.CERT_NONE)

            try:
                test_client.connect(host, port, keepalive=10)
                test_client.loop_start()
                start_t = time.time()
                while time.time() - start_t < timeout:
                    if connect_rc is not None and connect_rc != 0:
                        break
                    if sample_received is not None:
                        break
                    time.sleep(0.2)
            except Exception as ex:
                error_msg = str(ex)
            finally:
                try:
                    test_client.loop_stop()
                    test_client.disconnect()
                except Exception:
                    pass

        await loop.run_in_executor(None, run_test)

        if error_msg:
            return {"success": False, "message": f"Connection error: {error_msg}", "sample": None}
        if connect_rc != 0:
            return {"success": False, "message": f"Broker rejected connection (rc={connect_rc})", "sample": None}

        if sample_received:
            return {
                "success": True,
                "message": f"Connected and successfully received message on '{sample_received['topic']}'",
                "sample": sample_received,
            }
        else:
            return {
                "success": True,
                "message": f"Connected to broker successfully! (No message received on '{topic}' within {timeout}s timeout)",
                "sample": None,
            }


# Global singleton instance
mqtt_service = MQTTService()


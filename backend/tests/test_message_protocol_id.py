import unittest
from unittest.mock import MagicMock

from backend.app.p2p_community.message_protocol import MessageProtocol, MessageType


class TestMessageProtocolID(unittest.TestCase):
    def setUp(self):
        self.crypto_service = MagicMock()
        self.crypto_service.sign_message.return_value = "fake_signature"
        self.protocol = MessageProtocol(self.crypto_service)

    def test_provided_id_is_honored(self):
        custom_id = "test-uuid-12345"
        msg = self.protocol.create_message(
            sender_id="sender",
            recipient_id="recipient",
            message_type=MessageType.DIRECT,
            content={"text": "hello"},
            message_id=custom_id,
        )
        self.assertEqual(msg.message_id, custom_id)

    def test_default_id_generation(self):
        msg = self.protocol.create_message(
            sender_id="sender",
            recipient_id="recipient",
            message_type=MessageType.DIRECT,
            content={"text": "hello"},
        )
        self.assertTrue(msg.message_id.startswith("sender"))


if __name__ == "__main__":
    unittest.main()

import base64
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class CryptoService:
    def __init__(self, key_dir="keys"):
        self.key_dir = key_dir
        if not os.path.exists(key_dir):
            os.makedirs(key_dir)

        self.private_key_path = os.path.join(key_dir, "private_key.pem")
        self.public_key_path = os.path.join(key_dir, "public_key.pem")
        self.private_key = None
        self.public_key = None
        self._load_or_generate_keys()

    def _load_or_generate_keys(self):
        if os.path.exists(self.private_key_path) and os.path.exists(self.public_key_path):
            self._load_keys()
        else:
            self._generate_keys()

    def _generate_keys(self):
        self.private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )
        self.public_key = self.private_key.public_key()

        # Save Private Key
        with open(self.private_key_path, "wb") as f:
            f.write(
                self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        # Save Public Key
        with open(self.public_key_path, "wb") as f:
            f.write(
                self.public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )

    def _load_keys(self):
        with open(self.private_key_path, "rb") as f:
            self.private_key = serialization.load_pem_private_key(
                f.read(), password=None, backend=default_backend()
            )
        with open(self.public_key_path, "rb") as f:
            self.public_key = serialization.load_pem_public_key(f.read(), backend=default_backend())

    def get_public_key_string(self) -> str:
        pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return pem.decode("utf-8")

    def get_node_id(self) -> str:
        """Generate a consistent, URL-safe Node ID (SHA256 of Public Key)."""
        pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digest.update(pem)
        return digest.finalize().hex()

    def sign_message(self, message: str) -> str:
        signature = self.private_key.sign(
            message.encode("utf-8"),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def verify_signature(self, message: str, signature: str, public_key_pem: str) -> bool:
        """
        Verify a signature using the provided public key PEM string.
        Uses a local cache to avoid redundant PEM parsing.
        """
        if not public_key_pem:
            return False

        try:
            # 1. Check cache for already parsed key object
            if not hasattr(self, "_public_key_cache"):
                self._public_key_cache = {}

            if public_key_pem in self._public_key_cache:
                public_key = self._public_key_cache[public_key_pem]
            else:
                # 2. Parse and cache
                public_key = serialization.load_pem_public_key(
                    public_key_pem.encode("utf-8"), backend=default_backend()
                )
                # Keep cache size reasonable (simple eviction)
                if len(self._public_key_cache) > 500:
                    self._public_key_cache.clear()
                self._public_key_cache[public_key_pem] = public_key

            sig_bytes = base64.b64decode(signature)

            public_key.verify(
                sig_bytes,
                message.encode("utf-8"),
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False


crypto_service = CryptoService()

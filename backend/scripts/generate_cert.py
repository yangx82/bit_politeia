
import os
import secrets
import socket
from datetime import datetime, timedelta
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def generate_self_signed_cert(cert_path="keys/server.crt", key_path="keys/server.key", days=365):
    """Generates a self-signed certificate and private key."""
    
    # Ensure keys directory exists
    key_dir = os.path.dirname(cert_path)
    if not os.path.exists(key_dir):
        os.makedirs(key_dir)
        print(f"Created directory: {key_dir}")

    # Generate Private Key
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Generate CSR (Certificate Signing Request)
    # Using machine hostname and localhost
    hostname = socket.gethostname()
    
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"CN"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"State"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"City"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Bit Politeia"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
    ])

    alt_names = [
        x509.DNSName(u"localhost"),
        x509.DNSName(u"127.0.0.1"),
        x509.DNSName(u"0.0.0.0"),
        x509.DNSName(hostname)
    ]
    
    # Try to add local IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        alt_names.append(x509.IPAddress(type("IPv4Address", (object,), {"compressed": local_ip}))) # Pseudo-code if ipaddress module used, but x509 expects specific types.
        # Simpler: just use DNSName for IP string usually works for dev, or:
        import ipaddress
        alt_names.append(x509.IPAddress(ipaddress.ip_address(local_ip)))
        print(f"Added Subject Alternative Name: {local_ip}")
    except Exception as e:
        print(f"Warning: Could not detect local IP: {e}")

    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        subject
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.utcnow()
    ).not_valid_after(
        datetime.utcnow() + timedelta(days=days)
    ).add_extension(
        x509.SubjectAlternativeName(alt_names),
        critical=False,
    ).sign(key, hashes.SHA256())

    # Write Private Key
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    
    # Write Certificate
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print(f"✓ Private key saved to: {key_path}")
    print(f"✓ Certificate saved to: {cert_path}")
    print("\n[NOTE] Since this is a self-signed certificate, you will need to:")
    print("1. Allow invalid certificates in your client tests (verify=False)")
    print("2. Or add this certificate to your system's trusted root store.")

if __name__ == "__main__":
    generate_self_signed_cert()

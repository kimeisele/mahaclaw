"""Ahamkara — Identity / Crypto Signing.

Every envelope gets a cryptographic identity. This module provides:
- HMAC-SHA256 signing (stdlib, always available)
- ECDSA NIST256p signing (optional, if `ecdsa` pip package present)

Mirrors steward-protocol vibe_core/steward/crypto.py and
agent-city city/identity.py but respects the stdlib-only constraint.

Key storage: .mahaclaw/keys/
Fingerprint format: SHA-256(public_material)[:16] hex (matches federation)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

KEYS_DIR = Path(".mahaclaw/keys")
HMAC_KEY_FILE = KEYS_DIR / "hmac.key"
ECDSA_PRIVATE_FILE = KEYS_DIR / "private.pem"
ECDSA_PUBLIC_FILE = KEYS_DIR / "public.pem"


@dataclass(frozen=True, slots=True)
class Identity:
    """Maha Claw's signing identity."""
    fingerprint: str        # 16-char hex
    signing_method: str     # "ecdsa" or "hmac-sha256"
    public_material: str    # public key PEM or HMAC key fingerprint


def _ensure_keys_dir() -> None:
    KEYS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# HMAC-SHA256 (always available, stdlib-only)
# ---------------------------------------------------------------------------

def _load_or_generate_hmac_key() -> bytes:
    """Load or generate a 256-bit HMAC signing key."""
    _ensure_keys_dir()
    if HMAC_KEY_FILE.exists():
        return base64.b64decode(HMAC_KEY_FILE.read_text().strip())
    key = secrets.token_bytes(32)
    HMAC_KEY_FILE.write_text(base64.b64encode(key).decode() + "\n")
    os.chmod(HMAC_KEY_FILE, 0o600)
    return key


def hmac_sign(content: str) -> str:
    """Sign content with HMAC-SHA256. Returns base64-encoded signature."""
    key = _load_or_generate_hmac_key()
    sig = hmac.new(key, content.encode(), hashlib.sha256).digest()
    return base64.b64encode(sig).decode()


def hmac_verify(content: str, signature_b64: str) -> bool:
    """Verify an HMAC-SHA256 signature."""
    key = _load_or_generate_hmac_key()
    expected = hmac.new(key, content.encode(), hashlib.sha256).digest()
    try:
        actual = base64.b64decode(signature_b64)
    except Exception:
        return False
    return hmac.compare_digest(expected, actual)


def hmac_fingerprint() -> str:
    """Get fingerprint for the HMAC identity."""
    key = _load_or_generate_hmac_key()
    return hashlib.sha256(key).hexdigest()[:16]


# ---------------------------------------------------------------------------
# ECDSA NIST256p (optional, requires pip install ecdsa)
# ---------------------------------------------------------------------------

def _ecdsa_available() -> bool:
    try:
        import ecdsa  # noqa: F401
        return True
    except ImportError:
        return False


def _load_or_generate_ecdsa() -> tuple:
    """Returns (SigningKey, VerifyingKey) or raises ImportError."""
    from ecdsa import NIST256p, SigningKey

    _ensure_keys_dir()

    if ECDSA_PRIVATE_FILE.exists():
        sk = SigningKey.from_pem(ECDSA_PRIVATE_FILE.read_text())
        return sk, sk.verifying_key

    sk = SigningKey.generate(curve=NIST256p)
    vk = sk.verifying_key
    ECDSA_PRIVATE_FILE.write_text(sk.to_pem().decode())
    os.chmod(ECDSA_PRIVATE_FILE, 0o600)
    ECDSA_PUBLIC_FILE.write_text(vk.to_pem().decode())
    return sk, vk


def ecdsa_sign(content: str) -> str:
    """Sign content with ECDSA NIST256p. Returns base64-encoded signature."""
    from ecdsa.util import sigencode_string

    sk, _ = _load_or_generate_ecdsa()
    sig = sk.sign_deterministic(
        content.encode(),
        hashfunc=hashlib.sha256,
        sigencode=sigencode_string,
    )
    return base64.b64encode(sig).decode()


def ecdsa_verify(content: str, signature_b64: str, public_key_pem: str) -> bool:
    """Verify an ECDSA signature against content using a public key."""
    from ecdsa import VerifyingKey, BadSignatureError
    from ecdsa.util import sigdecode_string

    vk = VerifyingKey.from_pem(public_key_pem)
    try:
        vk.verify(
            base64.b64decode(signature_b64),
            content.encode(),
            hashfunc=hashlib.sha256,
            sigdecode=sigdecode_string,
        )
        return True
    except BadSignatureError:
        return False


def ecdsa_fingerprint() -> str:
    """Get SHA-256 fingerprint of ECDSA public key (16 hex chars)."""
    _, vk = _load_or_generate_ecdsa()
    return hashlib.sha256(vk.to_pem()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Unified API — auto-selects best available method
# ---------------------------------------------------------------------------

def sign_envelope(envelope: dict) -> str:
    """Sign an envelope's canonical content. Returns base64 signature.

    Signs: sorted JSON of (source, target, operation, nadi_type, priority,
    ttl_ms, envelope_id, correlation_id) — the immutable header fields.
    """
    canonical = _canonical_content(envelope)
    if _ecdsa_available():
        return ecdsa_sign(canonical)
    return hmac_sign(canonical)


def verify_envelope(envelope: dict) -> bool:
    """Verify an envelope's signature field."""
    sig = envelope.get("_signature", "")
    if not sig:
        return False
    canonical = _canonical_content(envelope)
    method = envelope.get("_signing_method", "hmac-sha256")
    if method == "ecdsa" and _ecdsa_available():
        pub = envelope.get("_signer_public_key", "")
        if pub:
            return ecdsa_verify(canonical, sig, pub)
    return hmac_verify(canonical, sig)


def get_identity() -> Identity:
    """Get current signing identity."""
    if _ecdsa_available():
        try:
            fp = ecdsa_fingerprint()
            _, vk = _load_or_generate_ecdsa()
            return Identity(
                fingerprint=fp,
                signing_method="ecdsa",
                public_material=vk.to_pem().decode(),
            )
        except Exception:
            pass
    return Identity(
        fingerprint=hmac_fingerprint(),
        signing_method="hmac-sha256",
        public_material=f"hmac:{hmac_fingerprint()}",
    )


def stamp_envelope(envelope: dict) -> dict:
    """Add Ahamkara identity fields to an envelope. Returns modified copy."""
    env = dict(envelope)
    identity = get_identity()
    sig = sign_envelope(env)
    env["_signature"] = sig
    env["_signer_fingerprint"] = identity.fingerprint
    env["_signing_method"] = identity.signing_method
    if identity.signing_method == "ecdsa":
        env["_signer_public_key"] = identity.public_material
    return env


def _canonical_content(envelope: dict) -> str:
    """Extract and serialize the canonical signable fields."""
    fields = {
        "source": envelope.get("source", ""),
        "target": envelope.get("target", ""),
        "operation": envelope.get("operation", ""),
        "nadi_type": envelope.get("nadi_type", ""),
        "priority": envelope.get("priority", ""),
        "ttl_ms": envelope.get("ttl_ms", 0),
        "envelope_id": envelope.get("envelope_id", ""),
        "correlation_id": envelope.get("correlation_id", ""),
    }
    return json.dumps(fields, sort_keys=True, separators=(",", ":"))

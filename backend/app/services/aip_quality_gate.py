"""
AIP Quality Gate Framework Service v3.0
=========================================
Production-grade Quality Gate for Agent Improvement Proposals (AIPs).

Implements:
- P0: Cryptographic Node Signature & Identity Binding (RSA-PSS via CryptoService)
- P0: Asynchronous Literature Authentication & Semantic Relevance (arXiv/DOI, with Fail-Safe fallback)
- P0: AST Syntax Validation & Dangerous Code Prevention (eval, exec, os.system)
- P0: AST Normalized Structural Fingerprint Deduplication
- P1: Description-Code Consistency & Inflation Auditing (Claim vs. AST Symbols)
- P1: Scope-Honesty & Atomic Enhancement Recognition ([Scope-Corrected])

Authors: Viki (0da9e18d), Aarron (9778108a), Bit Plato (5a40d9e6)
"""

import ast
import asyncio
import hashlib
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class Severity(Enum):
    """Quality Issue Severity Level."""
    P0 = "P0"  # Blocking: Hard barrier, proposal cannot be broadcast or accepted
    P1 = "P1"  # Warning: Soft assessment, delay or suggest correction
    P2 = "P2"  # Advisory: Informational observation


@dataclass
class QualityIssue:
    """Individual quality issue identified during evaluation."""
    severity: Severity
    category: str
    message: str
    details: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class QualityReport:
    """Comprehensive Quality Gate Assessment Report."""
    passed: bool
    issues: list[QualityIssue] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# ============================================================================
# Dimension 1: Asynchronous Academic Citation Verification
# ============================================================================

class AsyncCitationVerifier:
    """
    P0/P1: Asynchronous literature citation verification with fail-safe fallback.
    Queries arXiv / Crossref APIs with strict timeouts and local caching.
    """

    ARXIV_API_BASE = "https://export.arxiv.org/api/query"

    # Known hallucinated or frequently misattributed papers in agent evolution
    BLOCKLIST_CITATIONS = {
        "2408.00001": "Visual Diffusion Model paper frequently hallucinated for Cache/TTL proposals",
    }

    # Stopwords for academic keyword relevance check
    STOPWORDS = {
        "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
        "at", "by", "for", "with", "about", "against", "between", "into", "through",
        "during", "before", "after", "above", "below", "to", "from", "up", "down",
        "in", "out", "on", "off", "over", "under", "again", "further", "then",
        "once", "here", "there", "all", "any", "both", "each", "few", "more",
        "most", "other", "some", "such", "no", "nor", "not", "only", "own",
        "same", "so", "than", "too", "very", "can", "will", "just", "should",
        "now", "is", "are", "was", "were", "be", "been", "being", "have", "has",
        "had", "having", "do", "does", "did", "doing", "paper", "presents", "propose",
        "based", "approach", "method", "using", "via", "study", "new", "novel",
        "基于", "的", "和", "以及", "了", "在", "中", "与", "为", "由", "进行", "提出",
    }

    def __init__(self, cache_dir: Optional[str] = None):
        self._cache: dict[str, dict[str, Any]] = {}
        self.timeout = 6.0

    @staticmethod
    def extract_citations(text: str) -> list[str]:
        """Extracts arXiv IDs and DOIs from text."""
        if not text:
            return []
        patterns = [
            r'arXiv[:\.]\s*(\d{4}\.\d{4,5}(?:v\d+)?)',
            r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)',
            r'https?://doi\.org/([10]\.\d{4,9}/[-._;()/:A-Za-z0-9]+)',
        ]
        results = []
        for pat in patterns:
            matches = re.findall(pat, text, re.IGNORECASE)
            for m in matches:
                clean = m.strip().rstrip(".,;)")
                if clean and clean not in results:
                    results.append(clean)
        return results

    async def verify_citation(
        self,
        citation_id: str,
        claimed_topic: str = "",
        client: Optional[httpx.AsyncClient] = None,
    ) -> dict[str, Any]:
        """
        Asynchronously verifies an academic citation.
        Returns dict:
            exists: bool | None (None if unreachable/network error)
            title: str
            abstract: str
            relevant: bool
            is_unreachable: bool
            error: str | None
        """
        clean_id = re.sub(r'v\d+$', '', citation_id).strip()

        # 1. Check Blocklist
        if clean_id in self.BLOCKLIST_CITATIONS:
            return {
                "exists": True,
                "title": "Known Hallucinated Citation",
                "abstract": self.BLOCKLIST_CITATIONS[clean_id],
                "relevant": False,
                "is_unreachable": False,
                "error": f"Citation {clean_id} is blacklisted: {self.BLOCKLIST_CITATIONS[clean_id]}",
            }

        # 2. Check in-memory cache
        if clean_id in self._cache:
            cached = self._cache[clean_id]
            relevant = self._evaluate_relevance(claimed_topic, cached.get("title", ""), cached.get("abstract", ""))
            return {**cached, "relevant": relevant}

        # 3. Query arXiv API asynchronously
        url = f"{self.ARXIV_API_BASE}?id_list={clean_id}&max_results=1"
        should_close = False
        if client is None:
            client = httpx.AsyncClient(headers={"User-Agent": "BitPoliteia-QualityGate/3.0"}, timeout=self.timeout)
            should_close = True

        try:
            resp = await client.get(url)
            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning(f"[QualityGate] arXiv API rate-limited or unavailable: {resp.status_code}")
                return {
                    "exists": None,
                    "title": "",
                    "abstract": "",
                    "relevant": True,  # Fail-safe: don't reject on external outage
                    "is_unreachable": True,
                    "error": f"arXiv API returned HTTP {resp.status_code} (fail-safe fallback)",
                }

            content = resp.text
            if "<entry>" not in content or "<id>" not in content:
                res = {
                    "exists": False,
                    "title": "",
                    "abstract": "",
                    "relevant": False,
                    "is_unreachable": False,
                    "error": f"Citation '{clean_id}' does not exist on arXiv",
                }
                self._cache[clean_id] = res
                return res

            # Parse Atom XML
            root = ET.fromstring(content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entry = root.find("atom:entry", ns)
            if entry is None:
                return {
                    "exists": False,
                    "title": "",
                    "abstract": "",
                    "relevant": False,
                    "is_unreachable": False,
                    "error": f"Entry not found in XML response for {clean_id}",
                }

            title_elem = entry.find("atom:title", ns)
            title = " ".join(title_elem.text.split()) if title_elem is not None and title_elem.text else ""

            # Check if title indicates error
            if "Error" in title:
                return {
                    "exists": False,
                    "title": title,
                    "abstract": "",
                    "relevant": False,
                    "is_unreachable": False,
                    "error": f"arXiv returned error title: {title}",
                }

            summary_elem = entry.find("atom:summary", ns)
            abstract = " ".join(summary_elem.text.split()) if summary_elem is not None and summary_elem.text else ""

            relevant = self._evaluate_relevance(claimed_topic, title, abstract)

            result = {
                "exists": True,
                "title": title,
                "abstract": abstract,
                "relevant": relevant,
                "is_unreachable": False,
                "error": None,
            }
            self._cache[clean_id] = result
            return result

        except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError) as e:
            logger.warning(f"[QualityGate] arXiv API network error for {clean_id}: {e}")
            return {
                "exists": None,
                "title": "",
                "abstract": "",
                "relevant": True,  # Fail-safe: network failure should not falsely accuse node of fraud
                "is_unreachable": True,
                "error": f"Network unreachable during citation verification: {e}",
            }
        except Exception as e:
            logger.error(f"[QualityGate] Unexpected citation verification failure: {e}")
            return {
                "exists": None,
                "title": "",
                "abstract": "",
                "relevant": True,
                "is_unreachable": True,
                "error": f"Internal parser error: {e}",
            }
        finally:
            if should_close:
                await client.aclose()

    def _evaluate_relevance(self, claimed_topic: str, title: str, abstract: str) -> bool:
        """
        Evaluates semantic relevance using stopword-filtered keyword matching.
        """
        if not claimed_topic:
            return True

        topic_words = {
            w.lower().strip(".,;:()[]{}\"'")
            for w in re.split(r'[\s/_-]+', claimed_topic)
            if len(w) > 3 and w.lower() not in self.STOPWORDS
        }
        if not topic_words:
            return True

        content_words = {
            w.lower().strip(".,;:()[]{}\"'")
            for w in re.split(r'[\s/_-]+', f"{title} {abstract}")
            if len(w) > 3 and w.lower() not in self.STOPWORDS
        }

        overlap = topic_words & content_words
        overlap_ratio = len(overlap) / len(topic_words) if topic_words else 1.0
        return len(overlap) >= 1 or overlap_ratio >= 0.1


# ============================================================================
# Dimension 2: AST Consistency, Symbol Analysis & Inflation Auditing
# ============================================================================

class ASTConsistencyAuditor:
    """
    P0/P1: AST Consistency, dangerous syntax prevention, and description inflation auditing.
    """

    DANGEROUS_PATTERNS = [
        "eval(", "exec(", "os.system(", "__import__", "shutil.rmtree(", "subprocess.Popen(",
    ]

    INFLATION_INDICATORS = [
        "entire system", "complete engine", "full pipeline", "multi-tier framework",
        "end-to-end", "stream optimization", "complete overhaul", "全套架构", "整个系统",
    ]

    @staticmethod
    def parse_code(code: str) -> tuple[Optional[ast.Module], Optional[str]]:
        """Parses python code and checks for syntax validity."""
        clean = (code or "").strip()
        if not clean:
            return None, "Code diff is empty"
        try:
            tree = ast.parse(clean)
            return tree, None
        except SyntaxError as e:
            return None, f"SyntaxError at line {e.lineno}: {e.msg}"

    @classmethod
    def check_dangerous_code(cls, code: str) -> list[str]:
        """Detects prohibited dangerous execution patterns."""
        detected = []
        for pat in cls.DANGEROUS_PATTERNS:
            if pat in code:
                detected.append(pat)
        return detected

    @staticmethod
    def extract_ast_symbols(code: str, tree: ast.Module) -> dict[str, Any]:
        """Extracts declared classes, functions, methods, and LOC."""
        classes = []
        functions = []
        methods = []
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                classes.append({"name": node.name, "methods": class_methods})
                methods.extend(class_methods)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        lines = [l for l in code.splitlines() if l.strip() and not l.strip().startswith("#")]

        return {
            "classes": classes,
            "functions": functions,
            "methods": methods,
            "imports": imports,
            "non_empty_loc": len(lines),
            "all_symbol_names": {c["name"].lower() for c in classes} | {f.lower() for f in functions} | {m.lower() for m in methods},
        }

    @staticmethod
    def extract_claims_from_description(description: str) -> list[str]:
        """
        Extracts claimed functional features from description using multiple markdown patterns.
        """
        claims = []
        if not description:
            return []

        # 1. Numbered lists: (1) ... (2) ... or [1] ... [2] ...
        numbered_matches = re.findall(r'[\(\[]\d+[\)\]]\s*([^(\n\r]+?)(?=[\(\[]\d+[\)\]]|$)', description, re.DOTALL)
        for m in numbered_matches:
            c = m.strip().rstrip(",;.")
            if len(c) > 3:
                claims.append(c)

        # 2. Markdown bullet lists: "- feature" or "* feature" or "1. feature"
        bullet_matches = re.findall(r'^\s*[-*•\d\.]+\s+([^\n\r]+)', description, re.MULTILINE)
        for m in bullet_matches:
            c = m.strip().rstrip(",;.")
            if len(c) > 3:
                claims.append(c)

        # 3. Action phrases: implements/adds/provides/features
        action_matches = re.findall(
            r'(?:implements?|adds?|provides?|includes?|features?|实现|提供|支持)\s*[:\-]?\s*([^.,\n\r]+)',
            description,
            re.IGNORECASE,
        )
        for m in action_matches:
            c = m.strip().rstrip(",;.")
            if len(c) > 3:
                claims.append(c)

        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for c in claims:
            cl = c.lower()
            if cl not in seen and len(cl) > 3:
                seen.add(cl)
                deduped.append(c)

        return deduped[:20]

    @classmethod
    def audit_consistency_and_inflation(
        cls,
        description: str,
        code: str,
        tree: ast.Module,
        threshold: float = 0.6,
    ) -> dict[str, Any]:
        """
        Audits claimed features against actual AST symbols and detected code tokens.
        """
        symbols = cls.extract_ast_symbols(code, tree)
        claims = cls.extract_claims_from_description(description)
        code_lower = code.lower()
        symbol_names = symbols["all_symbol_names"]

        has_scope_tag = (
            "[Scope-Corrected" in description
            or "Non-Goals" in description
            or "[Atomic Enhancement" in description
        )

        verified_claims = []
        missing_claims = []

        for claim in claims:
            claim_lower = claim.lower()
            # Extract key identifiers from claim
            words = [w for w in re.split(r'[\s/_\-.:]+', claim_lower) if len(w) > 2]
            matched = False

            # Check if any symbol in AST matches key words from claim
            if any(w in symbol_names for w in words):
                matched = True
            elif any(w in code_lower for w in words if len(w) > 4):
                matched = True
            elif claim_lower in code_lower:
                matched = True

            if matched:
                verified_claims.append(claim)
            else:
                missing_claims.append(claim)

        total_claims = len(claims)
        coverage_ratio = len(verified_claims) / total_claims if total_claims > 0 else 1.0

        # Description inflation detection
        actual_symbol_count = max(len(symbols["classes"]) + len(symbols["functions"]), 1)
        inflation_ratio = round(total_claims / actual_symbol_count, 2)

        has_inflation_words = any(w in description.lower() for w in cls.INFLATION_INDICATORS)
        is_inflated = (inflation_ratio > 4.0 or has_inflation_words) and not has_scope_tag

        return {
            "coverage_ratio": round(coverage_ratio, 2),
            "verified_claims": verified_claims,
            "missing_claims": missing_claims,
            "total_claims": total_claims,
            "actual_symbols": symbols,
            "inflation_ratio": inflation_ratio,
            "is_inflated": is_inflated,
            "has_scope_tag": has_scope_tag,
            "passed": coverage_ratio >= threshold and not is_inflated,
        }


# ============================================================================
# Dimension 3: Cryptographic Identity & Signature Binding
# ============================================================================

class ProposalSignatureVerifier:
    """
    P0: Verifies proposal cryptographic signatures and binds to proposer Node ID.
    Prevents node ID spoofing (e.g. AIP-8A2B4B87 spoofing Viki).
    """

    @staticmethod
    def compute_node_id_from_public_key(public_key_pem: str) -> str:
        """Derives Node ID (SHA256 hex) from Public Key PEM."""
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes, serialization

        try:
            pk = serialization.load_pem_public_key(
                public_key_pem.encode("utf-8"),
                backend=default_backend(),
            )
            pem_bytes = pk.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
            digest.update(pem_bytes)
            return digest.finalize().hex()
        except Exception as e:
            logger.warning(f"[QualityGate] Failed to derive node_id from public key: {e}")
            return ""

    @staticmethod
    def get_canonical_proposal_payload(
        aip_id: str,
        initiator_id: str,
        title: str,
        description: str,
        proposed_diff: str,
    ) -> str:
        """Constructs canonical string payload for deterministic digital signature."""
        return f"{aip_id.strip()}::{initiator_id.strip()}::{title.strip()}::{description.strip()}::{proposed_diff.strip()}"

    @classmethod
    def verify_proposal_signature(
        cls,
        aip_id: str,
        initiator_id: str,
        title: str,
        description: str,
        proposed_diff: str,
        signature: str,
        public_key_pem: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Validates that:
        1. Signature and public_key_pem are present.
        2. public_key_pem mathematically derives into initiator_id (or prefix).
        3. Signature decrypts correctly against the canonical proposal payload.
        """
        if not signature or not public_key_pem:
            return False, "Missing cryptographic signature or public key"

        # Check Node ID identity binding
        derived_node_id = cls.compute_node_id_from_public_key(public_key_pem)
        if not derived_node_id:
            return False, "Invalid or malformed public_key_pem"

        clean_initiator = initiator_id.replace("node_", "").replace("-", "").lower()
        if not (derived_node_id.startswith(clean_initiator) or clean_initiator.startswith(derived_node_id[:8])):
            return False, f"Identity Spoofing Detected: Public key derives Node ID '{derived_node_id[:12]}', which does not match claimed initiator '{initiator_id}'"

        # Verify signature with CryptoService
        try:
            from .crypto_service import crypto_service
            payload = cls.get_canonical_proposal_payload(aip_id, initiator_id, title, description, proposed_diff)
            is_valid = crypto_service.verify_signature(payload, signature, public_key_pem)
            if not is_valid:
                return False, "Digital signature verification failed: payload has been modified or signature is invalid"
            return True, None
        except Exception as e:
            return False, f"Signature verification exception: {e}"


# ============================================================================
# Dimension 4: AST Structural Deduplication
# ============================================================================

class StructuralDuplicateDetector:
    """
    P0/P1: AST Normalized Structural Fingerprint deduplication.
    Normalizes identifiers, variable names, and comments to prevent superficial duplicate spam.
    """

    @staticmethod
    def compute_ast_fingerprint(code: str) -> str:
        """
        Computes a normalized structural AST fingerprint invariant to docstrings,
        comments, variable names, and formatting.
        """
        clean_code = (code or "").strip()
        if not clean_code:
            return ""

        try:
            tree = ast.parse(clean_code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    node.name = "_FUNC_"
                    if (
                        node.body
                        and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)
                    ):
                        node.body.pop(0)
                elif isinstance(node, ast.ClassDef):
                    node.name = "_CLASS_"
                    if (
                        node.body
                        and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)
                    ):
                        node.body.pop(0)
                elif isinstance(node, ast.arg):
                    node.arg = "_ARG_"
                elif isinstance(node, ast.Name):
                    node.id = "_VAR_"
                elif isinstance(node, ast.Attribute):
                    node.attr = "_ATTR_"

            raw_dump = ast.dump(tree, annotate_fields=False, include_attributes=False)
            return hashlib.sha256(raw_dump.encode("utf-8")).hexdigest()
        except Exception:
            lines = [
                re.sub(r"\s+", "", line.split("#")[0])
                for line in clean_code.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            normalized_text = "\n".join(lines)
            return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()

    @classmethod
    def check_duplicate(cls, code: str, known_fingerprints: dict[str, str]) -> tuple[bool, str]:
        """
        Checks if the code AST fingerprint matches any known proposal fingerprint.
        known_fingerprints: {aip_id: fingerprint}
        """
        new_fp = cls.compute_ast_fingerprint(code)
        if not new_fp:
            return False, ""
        for existing_id, existing_fp in known_fingerprints.items():
            if existing_fp == new_fp:
                return True, existing_id
        return False, ""


# ============================================================================
# Main Quality Gate Service Orchestrator
# ============================================================================

class QualityGateService:
    """
    Unified AIP Quality Gate Framework Engine.
    Orchestrates all deterministic and semantic audits before proposal submission or P2P voting.
    """

    def __init__(self):
        self.citation_verifier = AsyncCitationVerifier()
        self.known_fingerprints: dict[str, str] = {}

    def register_fingerprint(self, aip_id: str, code: str):
        """Registers a known code fingerprint for duplicate detection."""
        fp = StructuralDuplicateDetector.compute_ast_fingerprint(code)
        if fp:
            self.known_fingerprints[aip_id] = fp

    async def evaluate_proposal(
        self,
        aip_id: str,
        initiator_id: str,
        title: str,
        description: str,
        proposed_diff: str,
        research_sources: Optional[list[str]] = None,
        signature: str = "",
        public_key: str = "",
        require_signature: bool = False,
        exclude_aip_id: str = "",
    ) -> QualityReport:
        """
        Executes complete quality gate audit across P0 and P1 criteria.

        Args:
            aip_id: Unique AIP ID
            initiator_id: Node ID of proposal initiator
            title: Proposal title
            description: Detailed description
            proposed_diff: Python code modifications
            research_sources: List of citation URLs or IDs
            signature: Digital signature (base64)
            public_key: Public key PEM
            require_signature: Whether to enforce P0 signature check (True for P2P network verification)
            exclude_aip_id: AIP ID to exclude from duplicate check

        Returns:
            QualityReport with passed (True/False), issues list, and summary dict
        """
        issues: list[QualityIssue] = []

        # --------------------------------------------------------------------
        # P0 Check 1: Cryptographic Identity & Signature Binding
        # --------------------------------------------------------------------
        if require_signature or signature or public_key:
            sig_valid, sig_err = ProposalSignatureVerifier.verify_proposal_signature(
                aip_id=aip_id,
                initiator_id=initiator_id,
                title=title,
                description=description,
                proposed_diff=proposed_diff,
                signature=signature,
                public_key_pem=public_key,
            )
            if not sig_valid:
                issues.append(QualityIssue(
                    severity=Severity.P0,
                    category="identity_signature",
                    message=f"Cryptographic identity check failed: {sig_err}",
                    details=sig_err,
                ))

        # --------------------------------------------------------------------
        # P0 Check 2: AST Syntax & Dangerous Code Prevention
        # --------------------------------------------------------------------
        tree, syntax_err = ASTConsistencyAuditor.parse_code(proposed_diff)
        if tree is None:
            issues.append(QualityIssue(
                severity=Severity.P0,
                category="syntax",
                message=f"Code cannot be parsed by AST: {syntax_err}",
                details=syntax_err,
            ))
        else:
            dangerous = ASTConsistencyAuditor.check_dangerous_code(proposed_diff)
            if dangerous:
                issues.append(QualityIssue(
                    severity=Severity.P0,
                    category="security",
                    message=f"Prohibited dangerous execution pattern detected: {', '.join(dangerous)}",
                    details=f"Forbidden patterns: {dangerous}",
                ))

        # --------------------------------------------------------------------
        # P0 Check 3: Academic Citation Authentication & Relevance
        # --------------------------------------------------------------------
        citations_to_check = set()
        for src in (research_sources or []):
            extracted = AsyncCitationVerifier.extract_citations(src)
            citations_to_check.update(extracted)
        extracted_from_desc = AsyncCitationVerifier.extract_citations(description)
        citations_to_check.update(extracted_from_desc)

        claimed_topic = f"{title} {description[:200]}"
        for cid in citations_to_check:
            cit_res = await self.citation_verifier.verify_citation(cid, claimed_topic=claimed_topic)
            if cit_res.get("exists") is False:
                issues.append(QualityIssue(
                    severity=Severity.P0,
                    category="citation_fraud",
                    message=f"Academic citation '{cid}' does not exist (Fabricated/Hallucinated Citation)",
                    details=cit_res.get("error"),
                ))
            elif not cit_res.get("relevant"):
                issues.append(QualityIssue(
                    severity=Severity.P0,
                    category="citation_relevance",
                    message=f"Academic citation '{cid}' is irrelevant to proposal topic: {cit_res.get('title')}",
                    details=f"Paper Title: {cit_res.get('title')}",
                ))
            elif cit_res.get("is_unreachable"):
                # Fail-safe: Network error or 429 becomes P1 advisory rather than P0 crash
                issues.append(QualityIssue(
                    severity=Severity.P1,
                    category="citation_pending",
                    message=f"Citation '{cid}' could not be verified online due to network conditions: {cit_res.get('error')}",
                    details=cit_res.get("error"),
                ))

        # --------------------------------------------------------------------
        # P0 Check 4: AST Structural Deduplication
        # --------------------------------------------------------------------
        active_fps = {k: v for k, v in self.known_fingerprints.items() if k != exclude_aip_id and k != aip_id}
        is_dup, dup_id = StructuralDuplicateDetector.check_duplicate(proposed_diff, active_fps)
        if is_dup:
            issues.append(QualityIssue(
                severity=Severity.P0,
                category="duplicate_proposal",
                message=f"Proposed code is structurally duplicate of existing proposal '{dup_id}'",
                details=f"AST Fingerprint matches {dup_id}",
            ))

        # --------------------------------------------------------------------
        # P1 Check 5: Description-Code Consistency & Inflation Auditing
        # --------------------------------------------------------------------
        consistency_data = {}
        if tree is not None:
            consistency_data = ASTConsistencyAuditor.audit_consistency_and_inflation(
                description=description,
                code=proposed_diff,
                tree=tree,
                threshold=0.6,
            )
            if consistency_data.get("is_inflated"):
                issues.append(QualityIssue(
                    severity=Severity.P1,
                    category="description_inflation",
                    message=f"Description Inflation detected: claims {consistency_data.get('total_claims')} features vs {len(consistency_data.get('actual_symbols', {}).get('functions', []))} functions without [Scope-Corrected] declaration",
                    details=f"Inflation Ratio: {consistency_data.get('inflation_ratio')}",
                ))
            elif not consistency_data.get("passed"):
                issues.append(QualityIssue(
                    severity=Severity.P1,
                    category="consistency_gap",
                    message=f"Description-to-code coverage ratio low ({consistency_data.get('coverage_ratio'):.0%} < 60%). Missing: {consistency_data.get('missing_claims')[:3]}",
                    details=f"Missing claims: {consistency_data.get('missing_claims')}",
                ))

        # Check line count sanity
        loc = len([l for l in proposed_diff.splitlines() if l.strip() and not l.strip().startswith("#")])
        has_scope_tag = "[Scope-Corrected" in description or "Non-Goals" in description
        if loc < 15 and not has_scope_tag:
            issues.append(QualityIssue(
                severity=Severity.P1,
                category="code_brevity",
                message=f"Code diff is only {loc} LOC. Consider adding '[Scope-Corrected | Atomic Enhancement]' declaration to clarify non-goals.",
            ))

        # --------------------------------------------------------------------
        # Compilation & Report
        # --------------------------------------------------------------------
        p0_issues = [i for i in issues if i.severity == Severity.P0]
        p1_issues = [i for i in issues if i.severity == Severity.P1]
        passed = len(p0_issues) == 0

        summary = {
            "aip_id": aip_id,
            "passed": passed,
            "total_issues": len(issues),
            "p0_count": len(p0_issues),
            "p1_count": len(p1_issues),
            "code_loc": loc,
            "claims_coverage": consistency_data.get("coverage_ratio", 1.0),
            "citations_checked": len(citations_to_check),
            "has_scope_tag": has_scope_tag,
        }

        # Auto-register fingerprint if passed
        if passed and tree is not None:
            self.register_fingerprint(aip_id, proposed_diff)

        return QualityReport(
            passed=passed,
            issues=issues,
            summary=summary,
        )


quality_gate_service = QualityGateService()

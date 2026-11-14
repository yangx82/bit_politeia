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
from datetime import datetime, timezone
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
    OPENALEX_API_BASE = "https://api.openalex.org/works"

    # Known hallucinated or frequently misattributed papers in agent evolution
    BLOCKLIST_CITATIONS = {
        "2408.00001": "Visual Diffusion Model paper frequently hallucinated for Cache/TTL proposals",
    }

    # Computer Science / AI / Distributed Systems disciplines approved for Agent evolution
    CS_APPROVED_DISCIPLINES = {
        "computer science", "artificial intelligence", "distributed computing",
        "software engineering", "computer network", "machine learning",
        "algorithm", "operating system", "data structure", "cryptography",
        "peer-to-peer", "game theory", "mathematics", "information systems",
        "human-computer interaction", "cybersecurity", "theoretical computer science",
        "computational complexity", "database",
    }

    # Prohibited non-CS disciplines for Bit Politeia Agent protocol AIPs
    PROHIBITED_DISCIPLINES = {
        "medicine", "biology", "agricultural and food sciences", "agronomy",
        "immunology", "oncology", "pathology", "pharmacology", "genetics",
        "geology", "archaeology", "veterinary", "dermatology", "cardiology",
        "environmental science", "crop science", "zoology",
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
    def calculate_title_similarity(claimed_title: str, actual_title: str) -> float:
        """
        Calculates word token overlap (Jaccard similarity) between claimed and actual title.
        """
        if not claimed_title or not actual_title:
            return 0.0
        c_words = {
            w.lower().strip(".,;:()[]{}\"'")
            for w in re.split(r'[\s/_-]+', claimed_title)
            if len(w) > 2 and w.lower() not in AsyncCitationVerifier.STOPWORDS
        }
        a_words = {
            w.lower().strip(".,;:()[]{}\"'")
            for w in re.split(r'[\s/_-]+', actual_title)
            if len(w) > 2 and w.lower() not in AsyncCitationVerifier.STOPWORDS
        }
        if not c_words or not a_words:
            return 0.0
        intersection = c_words & a_words
        union = c_words | a_words
        return len(intersection) / len(union) if union else 0.0

    @classmethod
    def extract_claimed_title_for_citation(cls, cid: str, description: str = "", sources: Optional[list[str]] = None) -> str:
        """Extracts claimed paper title associated with a specific citation ID."""
        clean_cid = re.escape(cid.strip())
        for src in (sources or []):
            if cid in src:
                m1 = re.search(r'\(([^)]+)\)', src)
                if m1 and len(m1.group(1).strip()) > 5:
                    return m1.group(1).strip()
                m2 = re.search(r'([A-Za-z0-9\s:,\'-]{8,})\s*[-–—:]\s*' + clean_cid, src)
                if m2:
                    return m2.group(1).strip()
                m3 = re.search(clean_cid + r'\s*[-–—:]\s*([A-Za-z0-9\s:,\'-]{8,})', src)
                if m3:
                    return m3.group(1).strip()

        for line in (description or "").splitlines():
            if cid in line:
                m = re.search(clean_cid + r'[\s:–—\-]+([A-Za-z0-9\s:,\'-]{8,})', line)
                if m:
                    candidate = m.group(1).strip().rstrip(".,;)")
                    if len(candidate) > 6 and not candidate.startswith("http"):
                        return candidate
        return ""

    @staticmethod
    def extract_citations(text: str) -> list[str]:
        """Extracts arXiv IDs, DOIs, and OpenAlex Work IDs from text."""
        if not text:
            return []
        patterns = [
            r'arXiv[:\.]\s*(\d{4}\.\d{4,5}(?:v\d+)?)',
            r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)',
            r'https?://doi\.org/([10]\.\d{4,9}/[-._;()/:A-Za-z0-9]+)',
            r'openalex\.org/(?:works/)?(W\d+)',
            r'(?<![A-Za-z0-9])(W\d{8,11})(?![A-Za-z0-9])',
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
        claimed_title: str = "",
        client: Optional[httpx.AsyncClient] = None,
    ) -> dict[str, Any]:
        """
        Asynchronously verifies an academic citation (arXiv or OpenAlex).
        Returns dict:
            exists: bool | None (None if unreachable/network error)
            title: str
            abstract: str
            relevant: bool
            title_mismatch: bool
            title_similarity: float
            is_unreachable: bool
            discipline_mismatch: bool
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
                "title_mismatch": False,
                "title_similarity": 0.0,
                "is_unreachable": False,
                "discipline_mismatch": False,
                "error": f"Citation {clean_id} is blacklisted: {self.BLOCKLIST_CITATIONS[clean_id]}",
            }

        # 2. Check in-memory cache
        if clean_id in self._cache:
            cached = self._cache[clean_id]
            title = cached.get("title", "")
            title_mismatch = False
            sim = 1.0
            if claimed_title and title:
                sim = self.calculate_title_similarity(claimed_title, title)
                if sim < 0.40:
                    title_mismatch = True
            relevant = self._evaluate_relevance(claimed_topic, title, cached.get("abstract", "")) if not title_mismatch else False
            return {
                **cached,
                "relevant": relevant and not cached.get("discipline_mismatch", False),
                "title_mismatch": title_mismatch,
                "title_similarity": round(sim, 2),
                "error": f"Title mismatch: claimed '{claimed_title}' vs actual '{title}' (similarity={sim:.0%})" if title_mismatch else cached.get("error"),
            }

        should_close = False
        if client is None:
            client = httpx.AsyncClient(headers={"User-Agent": "BitPoliteia-QualityGate/3.0 (mailto:agent@bitpoliteia.org)"}, timeout=self.timeout)
            should_close = True

        try:
            # 3. Check if this is an OpenAlex Work ID (e.g. W7207867677)
            if re.match(r'^W\d+$', clean_id, re.IGNORECASE):
                return await self._verify_openalex(clean_id, claimed_topic, client, claimed_title=claimed_title)

            # 4. Query arXiv API asynchronously
            url = f"{self.ARXIV_API_BASE}?id_list={clean_id}&max_results=1"
            resp = await client.get(url)
            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning(f"[QualityGate] arXiv API rate-limited or unavailable: {resp.status_code}")
                return {
                    "exists": None,
                    "title": "",
                    "abstract": "",
                    "relevant": True,  # Fail-safe: don't reject on external outage
                    "title_mismatch": False,
                    "title_similarity": 1.0,
                    "is_unreachable": True,
                    "discipline_mismatch": False,
                    "error": f"arXiv API returned HTTP {resp.status_code} (fail-safe fallback)",
                }

            content = resp.text
            if "<entry>" not in content or "<id>" not in content:
                res = {
                    "exists": False,
                    "title": "",
                    "abstract": "",
                    "relevant": False,
                    "title_mismatch": False,
                    "title_similarity": 0.0,
                    "is_unreachable": False,
                    "discipline_mismatch": False,
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
                    "title_mismatch": False,
                    "title_similarity": 0.0,
                    "is_unreachable": False,
                    "discipline_mismatch": False,
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
                    "title_mismatch": False,
                    "title_similarity": 0.0,
                    "is_unreachable": False,
                    "discipline_mismatch": False,
                    "error": f"arXiv returned error title: {title}",
                }

            summary_elem = entry.find("atom:summary", ns)
            abstract = " ".join(summary_elem.text.split()) if summary_elem is not None and summary_elem.text else ""

            title_mismatch = False
            sim = 1.0
            if claimed_title and title:
                sim = self.calculate_title_similarity(claimed_title, title)
                if sim < 0.40:
                    title_mismatch = True

            relevant = self._evaluate_relevance(claimed_topic, title, abstract) if not title_mismatch else False

            result = {
                "exists": True,
                "title": title,
                "abstract": abstract,
                "relevant": relevant,
                "title_mismatch": title_mismatch,
                "title_similarity": round(sim, 2),
                "is_unreachable": False,
                "discipline_mismatch": False,
                "error": f"Title mismatch: claimed '{claimed_title}' vs actual '{title}' (similarity={sim:.0%})" if title_mismatch else None,
            }
            self._cache[clean_id] = result
            return result

        except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError) as e:
            logger.warning(f"[QualityGate] API network error for {clean_id}: {e}")
            return {
                "exists": None,
                "title": "",
                "abstract": "",
                "relevant": True,  # Fail-safe: network failure should not falsely accuse node of fraud
                "is_unreachable": True,
                "discipline_mismatch": False,
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
                "discipline_mismatch": False,
                "error": f"Internal parser error: {e}",
            }
        finally:
            if should_close:
                await client.aclose()

    async def _verify_openalex(
        self,
        work_id: str,
        claimed_topic: str,
        client: httpx.AsyncClient,
        claimed_title: str = "",
    ) -> dict[str, Any]:
        """
        Asynchronously verifies an academic citation via the OpenAlex API.
        Enforces discipline alignment (rejects biology, medicine, agronomy, etc.).
        """
        clean_id = work_id.upper().strip()
        url = f"{self.OPENALEX_API_BASE}/{clean_id}"
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                res = {
                    "exists": False,
                    "title": "",
                    "abstract": "",
                    "relevant": False,
                    "title_mismatch": False,
                    "title_similarity": 0.0,
                    "is_unreachable": False,
                    "discipline_mismatch": False,
                    "error": f"Citation '{clean_id}' does not exist on OpenAlex (HTTP 404)",
                }
                self._cache[clean_id] = res
                return res

            if resp.status_code == 429 or resp.status_code >= 500:
                logger.warning(f"[QualityGate] OpenAlex API rate-limited or unavailable: {resp.status_code}")
                return {
                    "exists": None,
                    "title": "",
                    "abstract": "",
                    "relevant": True,  # Fail-safe
                    "title_mismatch": False,
                    "title_similarity": 1.0,
                    "is_unreachable": True,
                    "discipline_mismatch": False,
                    "error": f"OpenAlex API returned HTTP {resp.status_code} (fail-safe fallback)",
                }

            data = resp.json()
            title = data.get("title") or ""

            # Reconstruct abstract from inverted index
            inv = data.get("abstract_inverted_index") or {}
            words = []
            for w, positions in inv.items():
                for p in positions:
                    words.append((p, w))
            words.sort(key=lambda x: x[0])
            abstract = " ".join(w for _, w in words)

            # Analyze disciplines from concepts and primary_topic
            concept_names = [
                c.get("display_name", "").lower()
                for c in data.get("concepts", [])
                if c.get("level", 0) <= 1
            ]
            primary_topic = data.get("primary_topic") or {}
            domain_name = (primary_topic.get("domain") or {}).get("display_name", "").lower()
            field_name = (primary_topic.get("field") or {}).get("display_name", "").lower()
            topic_name = primary_topic.get("display_name", "").lower()

            all_disciplines = set(concept_names) | {domain_name, field_name, topic_name}

            has_cs_alignment = any(
                any(cs in d for cs in self.CS_APPROVED_DISCIPLINES)
                for d in all_disciplines if d
            )
            has_prohibited_mismatch = any(
                any(prohib in d for prohib in self.PROHIBITED_DISCIPLINES)
                for d in all_disciplines if d
            )

            if has_prohibited_mismatch and not has_cs_alignment:
                detected_desc = f"{domain_name} / {field_name}" if domain_name else ", ".join(concept_names[:2])
                err_msg = (
                    f"Disciplinary Mismatch: Paper '{title[:40]}' belongs to '{detected_desc}' "
                    f"(Prohibited non-CS discipline for Agent protocol AIPs)"
                )
                logger.warning(f"[QualityGate] OpenAlex disciplinary mismatch for {clean_id}: {err_msg}")
                res = {
                    "exists": True,
                    "title": title,
                    "abstract": abstract,
                    "relevant": False,
                    "title_mismatch": False,
                    "title_similarity": 1.0,
                    "is_unreachable": False,
                    "discipline_mismatch": True,
                    "discipline_detected": detected_desc,
                    "error": err_msg,
                }
                self._cache[clean_id] = res
                return res

            title_mismatch = False
            sim = 1.0
            if claimed_title and title:
                sim = self.calculate_title_similarity(claimed_title, title)
                if sim < 0.40:
                    title_mismatch = True

            relevant = self._evaluate_relevance(claimed_topic, title, abstract) if not title_mismatch else False
            res = {
                "exists": True,
                "title": title,
                "abstract": abstract,
                "relevant": relevant,
                "title_mismatch": title_mismatch,
                "title_similarity": round(sim, 2),
                "is_unreachable": False,
                "discipline_mismatch": False,
                "error": f"Title mismatch: claimed '{claimed_title}' vs actual '{title}' (similarity={sim:.0%})" if title_mismatch else (None if relevant else f"Academic citation '{clean_id}' is semantically irrelevant to proposal topic"),
            }
            self._cache[clean_id] = res
            return res

        except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError) as e:
            logger.warning(f"[QualityGate] OpenAlex API network error for {clean_id}: {e}")
            return {
                "exists": None,
                "title": "",
                "abstract": "",
                "relevant": True,  # Fail-safe
                "title_mismatch": False,
                "title_similarity": 1.0,
                "is_unreachable": True,
                "discipline_mismatch": False,
                "error": f"Network unreachable during OpenAlex citation verification: {e}",
            }
        except Exception as e:
            logger.error(f"[QualityGate] Unexpected OpenAlex verification failure: {e}")
            return {
                "exists": None,
                "title": "",
                "abstract": "",
                "relevant": True,
                "title_mismatch": False,
                "title_similarity": 1.0,
                "is_unreachable": True,
                "discipline_mismatch": False,
                "error": f"Internal OpenAlex parser error: {e}",
            }

    def _evaluate_relevance(self, claimed_topic: str, title: str, abstract: str) -> bool:
        """
        Evaluates semantic relevance using stopword-filtered keyword matching.
        Requires at least 2 significant overlapping keywords or >= 20% topic words overlap.
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
        return len(overlap) >= 2 or overlap_ratio >= 0.20


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
        Strips explicit Non-Goals section first so explicitly excluded items are not flagged.
        """
        claims = []
        if not description:
            return []

        # Strip Non-Goals section before extracting positive feature claims
        target_text = re.split(
            r'(?:###?\s*🚫?\s*Non-Goals|Non-Goals\s*:|【非目标|非目标\s*[:：])',
            description,
            flags=re.IGNORECASE,
        )[0]

        # 1. Numbered lists: (1) ... (2) ... or [1] ... [2] ...
        numbered_matches = re.findall(r'[\(\[]\d+[\)\]]\s*([^(\n\r]+?)(?=[\(\[]\d+[\)\]]|$)', target_text, re.DOTALL)
        for m in numbered_matches:
            c = m.strip().rstrip(",;.")
            if len(c) > 3:
                claims.append(c)

        # 2. Markdown bullet lists: "- feature" or "* feature" or "1. feature"
        bullet_matches = re.findall(r'^\s*[-*•\d\.]+\s+([^\n\r]+)', target_text, re.MULTILINE)
        for m in bullet_matches:
            c = m.strip().rstrip(",;.")
            if len(c) > 3:
                claims.append(c)

        # 3. Action phrases: implements/adds/provides/features
        action_matches = re.findall(
            r'(?:implements?|adds?|provides?|includes?|features?|实现|提供|支持)\s*[:\-]?\s*([^.,\n\r]+)',
            target_text,
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
        
        # Hard Rule: If code is under 35 non-empty LOC and coverage is under 35%,
        # it is classified as severe inflation regardless of [Scope-Corrected] bypass tags.
        loc = symbols.get("non_empty_loc", 0)
        is_severe_empty_inflation = (loc < 35 and coverage_ratio < 0.35 and total_claims >= 2)

        is_inflated = is_severe_empty_inflation or ((inflation_ratio > 4.0 or has_inflation_words) and not has_scope_tag)
        is_blocking_consistency_gap = (coverage_ratio < threshold) or is_severe_empty_inflation

        return {
            "coverage_ratio": round(coverage_ratio, 2),
            "verified_claims": verified_claims,
            "missing_claims": missing_claims,
            "total_claims": total_claims,
            "actual_symbols": symbols,
            "inflation_ratio": inflation_ratio,
            "is_inflated": is_inflated,
            "is_blocking_consistency_gap": is_blocking_consistency_gap,
            "has_scope_tag": has_scope_tag,
            "passed": coverage_ratio >= threshold and not is_inflated,
        }

    @classmethod
    def check_semantic_antipatterns(cls, code: str, tree: ast.Module) -> list[QualityIssue]:
        """
        Detects deep semantic, algorithmic, and determinism anti-patterns in proposed code:
        1. Non-deterministic wall-clock calls (time.time / datetime.now) in audit/tally/hash/weight functions.
        2. Degenerate Quadratic Funding/Voting math (summing per-project before sqrt & square).
        3. Silent upward clamping of negative inputs via max(min_val, ...) without raising ValueError.
        4. Uninvoked test_...() functions in standalone verification scripts.
        5. Stateless lock theatre (acquiring self._lock on classes with zero mutable state).
        6. Duplicate ballot Sybil vulnerability in tally verification (Counter accumulation without deduplication).
        """
        issues: list[QualityIssue] = []
        clean_code = (code or "").strip()
        if not clean_code or tree is None:
            return issues

        loc = len([l for l in clean_code.splitlines() if l.strip() and not l.strip().startswith("#")])

        # 1. Check for uninvoked test_* functions at module level (for standalone scripts >= 25 LOC)
        top_level_test_defs = [
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        ]
        if top_level_test_defs and loc >= 25:
            # Check if any test function is called outside its own definition
            called_names = set()
            for stmt in tree.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                        called_names.add(sub.func.id)
            if not any(tf in called_names for tf in top_level_test_defs):
                issues.append(QualityIssue(
                    severity=Severity.P0,
                    category="uninvoked_test_suite",
                    message=(
                        f"Sandbox False-Positive Risk: Proposal defines test function(s) {top_level_test_defs} "
                        f"but never invokes them in module or __main__ scope."
                    ),
                    details=f"Uninvoked test functions: {top_level_test_defs}",
                ))

        # 2. Walk classes and methods for determinism, math fidelity, and input validation flaws
        deterministic_keywords = ("verify", "tally", "audit", "hash", "calculate_vote_weight", "compute_tally")
        time_Param_names = {"now", "reference_time", "current_time", "ref_time", "as_of", "eval_time", "snapshot_time"}

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fname = node.name.lower()
                arg_names = {a.arg.lower() for a in node.args.args}

                # 2a. Non-deterministic wall-clock time.time() / datetime.now() in audit/weight/hash methods
                if not fname.startswith("test_") and any(kw in fname for kw in deterministic_keywords):
                    has_wall_clock = False
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                            if sub.func.attr in ("time", "now", "utcnow") and isinstance(sub.func.value, ast.Name):
                                if sub.func.value.id in ("time", "datetime"):
                                    has_wall_clock = True
                    if has_wall_clock and not (arg_names & time_Param_names):
                        issues.append(QualityIssue(
                            severity=Severity.P0,
                            category="non_deterministic_audit",
                            message=(
                                f"Non-Deterministic Audit Defect: Function '{node.name}' calls wall-clock "
                                f"time.time()/datetime.now() without an injectable reference_time parameter, "
                                f"causing tally verification and cryptographic hashes to drift over time."
                            ),
                            details=f"Function '{node.name}' args={sorted(arg_names)}",
                        ))

                # 2b. Silent negative clamping in contribution/vote/stake methods
                if any(kw in fname for kw in ("add_contribution", "contribute", "stake", "cast_vote")):
                    func_src = ast.get_source_segment(clean_code, node) or ast.unparse(node)
                    has_max_clamp = "max(" in func_src and ("min_contribution" in func_src or "0.01" in func_src)
                    has_value_error = "ValueError" in func_src and ("amount" in func_src.split("ValueError")[0] or "<" in func_src)
                    # Check specifically if amount is clamped with max() without raising ValueError on negative amount
                    raises_on_negative = False
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Compare):
                            comp_src = ast.unparse(sub)
                            if "amount" in comp_src and ("<" in comp_src or "<=" in comp_src):
                                raises_on_negative = True
                    if has_max_clamp and not raises_on_negative:
                        issues.append(QualityIssue(
                            severity=Severity.P0,
                            category="silent_negative_clamping",
                            message=(
                                f"Input Validation Defect: Method '{node.name}' silently clamps negative/zero "
                                f"amounts upward via max() instead of raising ValueError."
                            ),
                            details=f"Method '{node.name}' clamps invalid negative inputs into positive contributions",
                        ))

                # 2c. Duplicate voter ballot accumulation in ProposalTallyAuditor.verify_tally
                if fname == "verify_tally":
                    func_src = ast.unparse(node)
                    if "Counter()" in func_src and "+= weight" in func_src and "len(set(" not in func_src:
                        issues.append(QualityIssue(
                            severity=Severity.P0,
                            category="tally_sybil_duplicate_ballot",
                            message=(
                                "Tally Audit Vulnerability: 'verify_tally' accumulates multiple entries from the "
                                "same voter_id via Counter += weight without rejecting duplicate voter ballots."
                            ),
                            details="Duplicate voter_id entries are summed rather than deduplicated or rejected.",
                        ))

            elif isinstance(node, ast.ClassDef):
                cls_src = ast.unparse(node)
                # 2d. Degenerate Quadratic Funding math: summing contributions per project before sqrt and **2
                if "Quadratic" in node.name or "quadratic" in cls_src.lower():
                    has_cumulative_project_sum = (
                        "_contributions[" in cls_src
                        and "+ amount" in cls_src
                        and "math.sqrt(" in cls_src
                        and "** 2" in cls_src
                    )
                    if has_cumulative_project_sum:
                        issues.append(QualityIssue(
                            severity=Severity.P0,
                            category="mathematical_fidelity_violation",
                            message=(
                                f"Mathematical Fidelity Violation in '{node.name}': Sums raw contributions per project "
                                f"before taking sqrt and squaring ((√Σc_i)² = Σc_i), which cancels out the square root "
                                f"and degenerates Quadratic Funding into linear allocation without whale/Sybil resistance."
                            ),
                            details="True CLR/QF requires summing individual √c_{p,i} across distinct contributors before squaring.",
                        ))

                # 2e. Stateless Lock Theatre detection
                init_methods = [
                    n for n in node.body
                    if isinstance(n, ast.FunctionDef) and n.name == "__init__"
                ]
                if init_methods:
                    init_node = init_methods[0]
                    self_attrs = set()
                    for sub in ast.walk(init_node):
                        if isinstance(sub, (ast.Assign, ast.AnnAssign)):
                            targets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
                            for t in targets:
                                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                                    self_attrs.add(t.attr)
                    if self_attrs == {"_lock"} or self_attrs == {"lock"}:
                        issues.append(QualityIssue(
                            severity=Severity.P0,
                            category="stateless_lock_theatre",
                            message=(
                                f"Stateless Lock Theatre in '{node.name}': Class holds zero mutable state in __init__ "
                                f"(only {sorted(self_attrs)}), making threading.Lock acquisition pure overhead."
                            ),
                            details=f"Class '{node.name}' has no mutable state attributes to protect.",
                        ))

        return issues


# ============================================================================
# Dimension 2.5: Repository AST Symbol Grounding & Collision Inspector
# ============================================================================

class RepoSymbolInspector:
    """
    Layer 1 (Agentless / SWE-agent Grounding):
    Inspects target repository files via AST to extract existing classes and functions,
    provides context skeletons for LLM prompts, and blocks proposals that blindly
    re-implement existing classes in target files.
    """

    @staticmethod
    def resolve_repo_path(rel_or_abs_path: str) -> str:
        """Resolves a relative repository file path (e.g. 'backend/app/...') to an absolute path."""
        if os.path.isabs(rel_or_abs_path) and os.path.exists(rel_or_abs_path):
            return rel_or_abs_path
        # Find repo root relative to this file (backend/app/services/aip_quality_gate.py)
        services_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(os.path.dirname(services_dir))
        repo_root = os.path.dirname(backend_dir)
        cand1 = os.path.join(repo_root, rel_or_abs_path.replace("/", os.sep))
        if os.path.exists(cand1):
            return cand1
        cand2 = os.path.join(backend_dir, rel_or_abs_path.replace("/", os.sep))
        if os.path.exists(cand2):
            return cand2
        return cand1

    @classmethod
    def extract_file_symbols(cls, file_path: str) -> dict[str, Any]:
        """Extracts top-level class names, methods, and functions from a repository Python file."""
        resolved = cls.resolve_repo_path(file_path)
        if not os.path.exists(resolved):
            return {"classes": {}, "functions": [], "exists": False}
        try:
            with open(resolved, "r", encoding="utf-8") as f:
                src = f.read()
            tree = ast.parse(src)
            classes: dict[str, list[str]] = {}
            functions: list[str] = []
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    methods = [
                        m.name for m in node.body
                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith("_")
                    ]
                    classes[node.name] = methods
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("test_"):
                        functions.append(node.name)
            return {"classes": classes, "functions": functions, "exists": True}
        except Exception as e:
            logger.debug(f"[RepoSymbolInspector] Failed to parse {resolved}: {e}")
            return {"classes": {}, "functions": [], "exists": False}

    @classmethod
    def build_target_files_skeleton(cls, target_files: list[str]) -> str:
        """Builds a concise AST symbol summary of target_files to ground the Planner & Coder LLMs."""
        if not target_files:
            return "No specific target files inspected."
        lines = []
        all_existing_classes = set()
        for tf in target_files:
            info = cls.extract_file_symbols(tf)
            if not info.get("exists"):
                continue
            cls_map = info.get("classes", {})
            all_existing_classes.update(cls_map.keys())
            cls_summaries = [
                f"{cname}({', '.join(meths[:5])})" if meths else cname
                for cname, meths in list(cls_map.items())[:25]
            ]
            lines.append(f"- `{tf}` already defines classes: {', '.join(cls_summaries) or 'None'}")
        if not lines:
            return "No existing classes found in target files."
        header = (
            "EXISTING REPOSITORY AST SYMBOLS IN TARGET FILES (DO NOT RE-IMPLEMENT OR DUPLICATE THESE CLASSES):\n"
            + "\n".join(lines)
            + f"\nFORBIDDEN EXISTING CLASS NAMES (must NOT be redefined): {sorted(all_existing_classes)}"
        )
        return header

    @classmethod
    def check_symbol_collision(cls, proposed_code: str, target_files: list[str]) -> list[dict[str, str]]:
        """
        Checks if proposed_code redefines top-level classes that already exist in target_files.
        Returns a list of collision dicts: [{'class_name': ..., 'target_file': ...}].
        """
        if not proposed_code or not target_files:
            return []
        try:
            tree = ast.parse(proposed_code.strip())
        except Exception:
            return []

        proposed_classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
        if not proposed_classes:
            return []

        collisions = []
        for tf in target_files:
            info = cls.extract_file_symbols(tf)
            existing_classes = set(info.get("classes", {}).keys())
            for p_cls in proposed_classes:
                if p_cls in existing_classes:
                    collisions.append({"class_name": p_cls, "target_file": tf})
        return collisions



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

    @staticmethod
    def compute_ast_shingles(code: str, k: int = 3) -> set[str]:
        """
        Extracts normalized AST node-type k-gram shingles and domain call signatures
        for fuzzy structural similarity detection (MAP-Elites / Clone Detection).
        """
        clean_code = (code or "").strip()
        if not clean_code:
            return set()
        try:
            tree = ast.parse(clean_code)
            node_seq = [
                type(n).__name__
                for n in ast.walk(tree)
                if not isinstance(n, (ast.Load, ast.Store, ast.Del, ast.expr_context))
            ]
            shingles = set()
            for i in range(max(0, len(node_seq) - k + 1)):
                shingles.add("->".join(node_seq[i : i + k]))
            return shingles
        except Exception:
            return set()

    @classmethod
    def compute_fuzzy_similarity(cls, code_a: str, code_b: str) -> float:
        """
        Computes combined AST shingle Jaccard similarity and class/method name overlap.
        """
        shingles_a = cls.compute_ast_shingles(code_a)
        shingles_b = cls.compute_ast_shingles(code_b)
        if not shingles_a or not shingles_b:
            return 0.0
        shingle_sim = len(shingles_a & shingles_b) / len(shingles_a | shingles_b)

        try:
            tree_a = ast.parse(code_a.strip())
            tree_b = ast.parse(code_b.strip())
            cls_a = {n.name.lower() for n in ast.walk(tree_a) if isinstance(n, ast.ClassDef)}
            cls_b = {n.name.lower() for n in ast.walk(tree_b) if isinstance(n, ast.ClassDef)}
            if cls_a and cls_b and (cls_a & cls_b):
                # Boost similarity when defining identical class names with similar AST structure
                return min(1.0, shingle_sim * 0.7 + 0.35)
        except Exception:
            pass
        return shingle_sim

    @classmethod
    def check_fuzzy_duplicate(
        cls,
        code: str,
        known_codes: dict[str, str],
        threshold: float = 0.78,
    ) -> tuple[bool, str, float]:
        """
        Checks if proposed code is a near-duplicate variant of any known code snippet.
        Returns (is_near_duplicate, matched_aip_id, similarity_score).
        """
        for existing_id, existing_code in known_codes.items():
            sim = cls.compute_fuzzy_similarity(code, existing_code)
            if sim >= threshold:
                return True, existing_id, round(sim, 3)
        return False, "", 0.0


# ============================================================================
# Dimension 5: Execution-Guided Test Discovery & AST Micro-Mutation Tester
# ============================================================================

class ASTMutationTester:
    """
    Layer 4 (Meta TestGen-LLM / MuTAP Mutation Gate):
    1. Discovers all `test_*` functions in proposed code and forces execution.
    2. Generates single-point AST mutants of the production logic (operator flips,
       constant perturbations) and executes the test suite against each mutant.
    3. Computes mutation kill rate to reject tautological/weak test suites.
    """

    @classmethod
    def generate_ast_mutants(cls, code: str, max_mutants: int = 4) -> list[tuple[str, str]]:
        """
        Generates up to `max_mutants` single-point mutated Python source strings
        targeting non-test functions/methods.
        Returns list of (mutant_description, mutated_code_str).
        """
        clean = (code or "").strip()
        if not clean:
            return []
        try:
            base_tree = ast.parse(clean)
        except Exception:
            return []

        mutants: list[tuple[str, str]] = []

        # Collect candidate mutation sites inside non-test functions/classes
        # Site types: ('binop', idx), ('cmpop', idx), ('const_num', idx)
        sites: list[tuple[str, int, str]] = []
        node_idx = 0
        for stmt in base_tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name.startswith("test_"):
                continue
            if isinstance(stmt, ast.If):
                continue
            for sub in ast.walk(stmt):
                node_idx += 1
                if isinstance(sub, ast.BinOp) and isinstance(
                    sub.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
                ):
                    sites.append(("binop", node_idx, type(sub.op).__name__))
                elif isinstance(sub, ast.Compare) and len(sub.ops) == 1 and isinstance(
                    sub.ops[0], (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq)
                ):
                    sites.append(("cmpop", node_idx, type(sub.ops[0]).__name__))

        for site_type, target_idx, op_name in sites:
            if len(mutants) >= max_mutants:
                break
            tree_copy = ast.parse(clean)
            curr_idx = 0
            mutated_desc = ""
            for stmt in tree_copy.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name.startswith("test_"):
                    continue
                if isinstance(stmt, ast.If):
                    continue
                for sub in ast.walk(stmt):
                    curr_idx += 1
                    if curr_idx == target_idx:
                        if site_type == "binop" and isinstance(sub, ast.BinOp):
                            if isinstance(sub.op, ast.Add):
                                sub.op = ast.Sub()
                                mutated_desc = "Flip BinOp Add(+) -> Sub(-)"
                            elif isinstance(sub.op, ast.Sub):
                                sub.op = ast.Add()
                                mutated_desc = "Flip BinOp Sub(-) -> Add(+)"
                            elif isinstance(sub.op, ast.Mult):
                                sub.op = ast.Div()
                                mutated_desc = "Flip BinOp Mult(*) -> Div(/)"
                            elif isinstance(sub.op, ast.Div):
                                sub.op = ast.Mult()
                                mutated_desc = "Flip BinOp Div(/) -> Mult(*)"
                            elif isinstance(sub.op, ast.Pow):
                                sub.op = ast.Mult()
                                mutated_desc = "Flip BinOp Pow(**) -> Mult(*)"
                        elif site_type == "cmpop" and isinstance(sub, ast.Compare):
                            op0 = sub.ops[0]
                            if isinstance(op0, ast.Lt):
                                sub.ops[0] = ast.GtE()
                                mutated_desc = "Flip Compare Lt(<) -> GtE(>=)"
                            elif isinstance(op0, ast.LtE):
                                sub.ops[0] = ast.Gt()
                                mutated_desc = "Flip Compare LtE(<=) -> Gt(>)"
                            elif isinstance(op0, ast.Gt):
                                sub.ops[0] = ast.LtE()
                                mutated_desc = "Flip Compare Gt(>) -> LtE(<=)"
                            elif isinstance(op0, ast.GtE):
                                sub.ops[0] = ast.Lt()
                                mutated_desc = "Flip Compare GtE(>=) -> Lt(<)"
                            elif isinstance(op0, ast.Eq):
                                sub.ops[0] = ast.NotEq()
                                mutated_desc = "Flip Compare Eq(==) -> NotEq(!=)"
            if mutated_desc:
                try:
                    ast.fix_missing_locations(tree_copy)
                    mutated_src = ast.unparse(tree_copy)
                    if mutated_src != clean:
                        mutants.append((mutated_desc, mutated_src))
                except Exception:
                    pass

        return mutants

    @classmethod
    def run_in_process_verification(
        cls,
        code: str,
        min_kill_rate: float = 0.50,
    ) -> dict[str, Any]:
        """
        Executes the proposed code, discovers and runs all `test_*` functions,
        and evaluates AST micro-mutants against those `test_*` functions.
        """
        clean = (code or "").strip()
        if not clean:
            return {"passed": False, "error": "Empty code", "tests_run": 0, "mutation_kill_rate": 0.0}

        try:
            tree = ast.parse(clean)
        except SyntaxError as e:
            return {"passed": False, "error": f"SyntaxError: {e}", "tests_run": 0, "mutation_kill_rate": 0.0}

        test_func_names = [
            n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")
        ]
        top_level_asserts = [
            n for n in tree.body if isinstance(n, ast.Assert)
        ]

        # Check if test functions were defined but never invoked in the original script
        called_names = set()
        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                    called_names.add(sub.func.id)
        uninvoked_tests = [tf for tf in test_func_names if tf not in called_names]

        # Strip `if __name__ == "__main__":` when building reusable module namespace
        module_tree = ast.parse(clean)
        module_tree.body = [
            stmt for stmt in module_tree.body
            if not (
                isinstance(stmt, ast.If)
                and "__name__" in ast.unparse(stmt.test)
            )
        ]
        module_src = ast.unparse(module_tree)

        # 1. Execute base module and run all discovered test_* functions
        ns: dict[str, Any] = {"__name__": "__aip_sandbox__"}
        try:
            exec(compile(module_src, "<aip_candidate>", "exec"), ns)
            for tf_name in test_func_names:
                fn = ns.get(tf_name)
                if callable(fn):
                    fn()
        except Exception as e:
            return {
                "passed": False,
                "error": f"Unit test execution failed: {type(e).__name__}: {e}",
                "tests_run": len(test_func_names),
                "uninvoked_tests": uninvoked_tests,
                "mutation_kill_rate": 0.0,
            }

        total_tests = len(test_func_names) + len(top_level_asserts)
        if total_tests == 0:
            return {
                "passed": False,
                "error": "No unit tests (def test_* or assert) found in proposed code.",
                "tests_run": 0,
                "uninvoked_tests": [],
                "mutation_kill_rate": 0.0,
            }

        # 2. Run AST Micro-Mutation Testing against discovered test_* functions
        mutants = cls.generate_ast_mutants(module_src, max_mutants=4)
        killed = 0
        survived_descriptions = []

        if mutants and test_func_names:
            for desc, m_src in mutants:
                m_ns: dict[str, Any] = {"__name__": "__aip_mutant__"}
                mutant_killed = False
                try:
                    exec(compile(m_src, "<aip_mutant>", "exec"), m_ns)
                    for tf_name in test_func_names:
                        fn = m_ns.get(tf_name)
                        if callable(fn):
                            fn()
                except Exception:
                    mutant_killed = True

                if mutant_killed:
                    killed += 1
                else:
                    survived_descriptions.append(desc)

            kill_rate = killed / len(mutants)
        else:
            kill_rate = 1.0

        passed = (kill_rate >= min_kill_rate) and (len(uninvoked_tests) == 0)
        err_reasons = []
        if uninvoked_tests:
            err_reasons.append(f"Uninvoked test functions detected: {uninvoked_tests}")
        if kill_rate < min_kill_rate:
            err_reasons.append(
                f"Low mutation kill rate ({kill_rate:.0%} < {min_kill_rate:.0%}); "
                f"survived mutants: {survived_descriptions}"
            )

        return {
            "passed": passed,
            "error": "; ".join(err_reasons) if err_reasons else None,
            "tests_run": total_tests,
            "tests_executed": test_func_names,
            "uninvoked_tests": uninvoked_tests,
            "mutants_total": len(mutants),
            "mutants_killed": killed,
            "mutation_kill_rate": round(kill_rate, 2),
            "survived_mutants": survived_descriptions,
        }


# ============================================================================
# Main Quality Gate Service Orchestrator
# ============================================================================

class QualityGateService:
    """
    Unified AIP Quality Gate Framework Engine.
    Orchestrates all deterministic and semantic audits before proposal submission or P2P voting.
    """

    def __init__(self, data_dir: Optional[str] = None):
        self.citation_verifier = AsyncCitationVerifier()
        self.known_fingerprints: dict[str, str] = {}
        self.known_codes: dict[str, str] = {}
        if data_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.data_dir = os.path.join(base_dir, "data")
        else:
            self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.rejected_fingerprints_file = os.path.join(self.data_dir, "historical_rejected_fingerprints.json")
        self.rejected_fingerprints: dict[str, dict[str, Any]] = {}
        self._load_rejected_fingerprints()

    def _load_rejected_fingerprints(self):
        if os.path.exists(self.rejected_fingerprints_file):
            try:
                with open(self.rejected_fingerprints_file, "r", encoding="utf-8") as f:
                    self.rejected_fingerprints = json.load(f)
            except Exception as e:
                logger.warning(f"[QualityGate] Failed to load rejected fingerprints: {e}")

    def register_rejected_fingerprint(self, aip_id: str, code: str, reason: str = ""):
        """Registers and persists an AST fingerprint of a rejected proposal to prevent repeat submissions."""
        fp = StructuralDuplicateDetector.compute_ast_fingerprint(code)
        if fp:
            self.rejected_fingerprints[fp] = {
                "aip_id": aip_id,
                "reason": reason[:200],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            try:
                with open(self.rejected_fingerprints_file, "w", encoding="utf-8") as f:
                    json.dump(self.rejected_fingerprints, f, indent=2, ensure_ascii=False)
                logger.info(f"[QualityGate] Persisted rejected proposal AST fingerprint for {aip_id} ({fp[:8]})")
            except Exception as e:
                logger.warning(f"[QualityGate] Failed to save rejected fingerprints: {e}")

    def register_fingerprint(self, aip_id: str, code: str):
        """Registers a known code fingerprint and source for exact and fuzzy duplicate detection."""
        fp = StructuralDuplicateDetector.compute_ast_fingerprint(code)
        if fp:
            self.known_fingerprints[aip_id] = fp
        if code and code.strip():
            self.known_codes[aip_id] = code.strip()

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
        target_files: Optional[list[str]] = None,
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
            target_files: Optional list of target repository files to check for symbol collision

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
        # P0 Check 2: AST Syntax, Dangerous Code & Semantic Anti-Patterns
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
            # Check deep semantic & algorithmic anti-patterns
            antipattern_issues = ASTConsistencyAuditor.check_semantic_antipatterns(proposed_diff, tree)
            issues.extend(antipattern_issues)

        # --------------------------------------------------------------------
        # P0 Check 2.5: Repository AST Symbol Collision Gate (Layer 1)
        # --------------------------------------------------------------------
        if tree is not None and target_files:
            collisions = RepoSymbolInspector.check_symbol_collision(proposed_diff, target_files)
            if collisions:
                coll_strs = [f"'{c['class_name']}' in {c['target_file']}" for c in collisions]
                issues.append(QualityIssue(
                    severity=Severity.P0,
                    category="repo_symbol_collision",
                    message=(
                        f"Repository Symbol Collision / Reinvention: Proposal redefines existing class(es) "
                        f"{', '.join(coll_strs)}. Extend or integrate with existing classes instead of duplicating them."
                    ),
                    details=f"Collisions: {collisions}",
                ))

        # --------------------------------------------------------------------
        # P0 Check 3: Academic Citation Authentication, Relevance & Title Matching
        # --------------------------------------------------------------------
        citations_to_check = set()
        for src in (research_sources or []):
            extracted = AsyncCitationVerifier.extract_citations(src)
            citations_to_check.update(extracted)
        extracted_from_desc = AsyncCitationVerifier.extract_citations(description)
        citations_to_check.update(extracted_from_desc)

        claimed_topic = f"{title} {description[:200]}"
        for cid in citations_to_check:
            claimed_title = AsyncCitationVerifier.extract_claimed_title_for_citation(cid, description, research_sources)
            cit_res = await self.citation_verifier.verify_citation(cid, claimed_topic=claimed_topic, claimed_title=claimed_title)
            if cit_res.get("exists") is False:
                issues.append(QualityIssue(
                    severity=Severity.P0,
                    category="citation_fraud",
                    message=f"Academic citation '{cid}' does not exist (Fabricated/Hallucinated Citation)",
                    details=cit_res.get("error"),
                ))
            elif cit_res.get("title_mismatch"):
                issues.append(QualityIssue(
                    severity=Severity.P0,
                    category="citation_title_mismatch",
                    message=f"Academic citation title mismatch for '{cid}': {cit_res.get('error')}",
                    details=cit_res.get("error"),
                ))
            elif not cit_res.get("relevant"):
                is_mismatch = cit_res.get("discipline_mismatch", False)
                category = "citation_discipline_mismatch" if is_mismatch else "citation_relevance"
                msg_prefix = "Academic citation disciplinary mismatch" if is_mismatch else "Academic citation is irrelevant"
                issues.append(QualityIssue(
                    severity=Severity.P0,
                    category=category,
                    message=f"{msg_prefix} for '{cid}': {cit_res.get('title')}",
                    details=cit_res.get("error") or f"Paper Title: {cit_res.get('title')}",
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
        # P0 Check 4: AST Structural & Fuzzy Deduplication (Active & Rejected)
        # --------------------------------------------------------------------
        # 4.1 Check exact fingerprint against actively tracked proposals
        active_fps = {k: v for k, v in self.known_fingerprints.items() if k != exclude_aip_id and k != aip_id}
        is_dup, dup_id = StructuralDuplicateDetector.check_duplicate(proposed_diff, active_fps)
        if is_dup:
            issues.append(QualityIssue(
                severity=Severity.P0,
                category="duplicate_proposal",
                message=f"Proposed code is structurally duplicate of existing proposal '{dup_id}'",
                details=f"AST Fingerprint matches {dup_id}",
            ))
        else:
            # 4.1b Check fuzzy AST shingle similarity against known proposal codes
            active_codes = {k: v for k, v in self.known_codes.items() if k != exclude_aip_id and k != aip_id}
            is_fuzzy_dup, fuzzy_id, fuzzy_sim = StructuralDuplicateDetector.check_fuzzy_duplicate(
                proposed_diff, active_codes, threshold=0.78
            )
            if is_fuzzy_dup:
                issues.append(QualityIssue(
                    severity=Severity.P0,
                    category="near_duplicate_variant",
                    message=(
                        f"Near-Duplicate Variant Detected: Proposed code shares {fuzzy_sim:.0%} structural/symbol "
                        f"similarity with existing proposal '{fuzzy_id}'."
                    ),
                    details=f"Fuzzy AST similarity={fuzzy_sim:.3f} with {fuzzy_id}",
                ))

        # 4.2 Check against historically rejected proposal templates
        new_fp = StructuralDuplicateDetector.compute_ast_fingerprint(proposed_diff)
        if new_fp and new_fp in self.rejected_fingerprints:
            rej_meta = self.rejected_fingerprints[new_fp]
            orig_id = rej_meta.get("aip_id", "historical")
            issues.append(QualityIssue(
                severity=Severity.P0,
                category="duplicate_of_rejected_proposal",
                message=f"Proposed code AST is a structural duplicate of previously rejected proposal '{orig_id}'",
                details=f"AST Fingerprint matches rejected proposal {orig_id}. Re-submitting rejected code templates without structural fixes is prohibited.",
            ))

        # --------------------------------------------------------------------
        # P0/P1 Check 5: Description-Code Consistency & Inflation Auditing
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
                    severity=Severity.P0,  # Elevated to P0 Hard Barrier
                    category="description_inflation_blocking",
                    message=f"Description Inflation detected: claims {consistency_data.get('total_claims')} features vs {len(consistency_data.get('actual_symbols', {}).get('functions', []))} functions (claims coverage={consistency_data.get('coverage_ratio'):.0%})",
                    details=f"Inflation Ratio: {consistency_data.get('inflation_ratio')}",
                ))
            elif consistency_data.get("is_blocking_consistency_gap"):
                issues.append(QualityIssue(
                    severity=Severity.P0,  # Elevated to P0 Hard Barrier
                    category="consistency_gap_blocking",
                    message=f"Description-to-code claims coverage ratio is critically low ({consistency_data.get('coverage_ratio'):.0%} < 60%). Missing: {consistency_data.get('missing_claims')[:3]}",
                    details=f"Missing claims: {consistency_data.get('missing_claims')}",
                ))
            elif not consistency_data.get("passed"):
                issues.append(QualityIssue(
                    severity=Severity.P1,
                    category="consistency_gap",
                    message=f"Description-to-code coverage ratio warning ({consistency_data.get('coverage_ratio'):.0%}). Missing: {consistency_data.get('missing_claims')[:3]}",
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

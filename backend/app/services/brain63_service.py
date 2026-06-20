"""
Brain63 Knowledge Service — READ-ONLY vault retrieval for SILVIA.

SILVIA may ONLY read from Brain63.
Writing, editing, creating, or deleting Brain63 notes is strictly forbidden.
All factual content is attributed to Brain63 as the authoritative source.

Search strategy: keyword shortlist (token overlap + entity/type boosts),
no network calls, all file I/O, index cached for 5 minutes.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# ── Skip lists ──────────────────────────────────────────────────────────────

_SKIP_FILES = {
    "DECISION_TEMPLATE.md",
    "LESSONS_LEARNED_TEMPLATE.md",
    "PROJECT_STATUS_TEMPLATE.md",
    "ROADMAP_TEMPLATE.md",
    "DAILY_LOG_TEMPLATE.md",
    "WEEKLY_REVIEW_TEMPLATE.md",
    "OVERVIEW_TEMPLATE.md",
}

_SKIP_DIRS = {".obsidian", ".git", "14_Daily_Logs", "15_Weekly_Reviews"}

# ── Query-type → preferred file name ────────────────────────────────────────

_TYPE_FILE_PRIORITY: dict[str, list[str]] = {
    "status":    ["Status.md", "HiveFC_Status.md", "CURRENT_STATE.md"],
    "overview":  ["Overview.md", "README.md"],
    "decisions": ["Decisions.md", "HiveFC_Decisions.md", "PROJECT_OWNERSHIP_DECISIONS.md"],
    "hardware":  ["Status.md", "Overview.md", "HARDWARE_INVENTORY_DETAILED_2026.md"],
    "roadmap":   ["Roadmap.md"],
    "vision":    ["Vision.md", "KOI_DEEP_VISION.md", "DRONEHIVE_ORIGIN_AND_VISION.md"],
    "general":   [],  # no file priority — keyword-only
}

# ── Entity → canonical Brain63 project folder name ───────────────────────────
# Used to match vault folder structure to query entity names.

_ENTITY_TO_PROJECT: dict[str, str] = {
    "nighthawk":   "Nighthawk",
    "cyberdeck":   "Cyberdeck",
    "dronehive":   "DroneHive",
    "droneHive":   "DroneHive",
    "drone hive":  "DroneHive",
    "drone-hive":  "DroneHive",
    "koi":         "KOI",
    "brain63":     "Brain63",
    "brain 63":    "Brain63",
    "silvia":      "CMD-CTR",
    "cmd-ctr":     "CMD-CTR",
    "cmdctr":      "CMD-CTR",
    "cmd ctr":     "CMD-CTR",
    "university":  "University",
    "magi":        "MAGI",
    "artoo":       "Artoo",
    "fpv":         "FPV_Aircraft",
    "bespoke":     "BespokeToMe",
    "bespoketome": "BespokeToMe",
    "freeguy":     "ProjFreeGuy",
    "free guy":    "ProjFreeGuy",
}


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class ChunkResult:
    file_path: str   # relative to vault root, forward slashes
    project: str     # from frontmatter or inferred from path
    note_type: str   # status / overview / decisions / roadmap / hardware / note
    section: str     # section heading ("" for root/preamble)
    content: str     # chunk text (stripped)
    score: float = 0.0


@dataclass
class Brain63Answer:
    text: str              # formatted answer for SILVIA to return
    confidence: str        # "high" / "medium" / "low"
    sources: list[str] = field(default_factory=list)  # relative file paths used


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"\w+", text) if len(w) > 2}


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except Exception:
        fm = {}
    return fm, text[end + 3:].strip()


def _split_by_headers(body: str) -> list[tuple[str, str]]:
    """Split markdown body into (heading, content) pairs by ## / ### headers."""
    lines = body.split("\n")
    sections: list[tuple[str, str]] = []
    cur_heading = ""
    cur_lines: list[str] = []
    for line in lines:
        if line.startswith("## ") or line.startswith("### "):
            body_so_far = "\n".join(cur_lines).strip()
            if body_so_far:
                sections.append((cur_heading, body_so_far))
            cur_heading = line.lstrip("# ").strip()
            cur_lines = []
        else:
            cur_lines.append(line)
    tail = "\n".join(cur_lines).strip()
    if tail:
        sections.append((cur_heading, tail))
    return sections


def _infer_project(rel_path: Path) -> str:
    """Infer project name from vault-relative file path."""
    parts = rel_path.parts
    if len(parts) >= 2:
        folder = parts[-2]
        if not re.match(r"^\d+_", folder) and folder not in ("Brain63",):
            return folder
    return ""


def _infer_type(filename: str) -> str:
    stem = filename.replace(".md", "").lower()
    mapping = {
        "status": "status",
        "overview": "overview",
        "decisions": "decisions",
        "roadmap": "roadmap",
        "architecture": "architecture",
        "lessons_learned": "lessons_learned",
        "readme": "overview",
        "vision": "vision",
    }
    for key, val in mapping.items():
        if key in stem:
            return val
    return "note"


def _bullet_items(content: str, max_items: int = 3) -> list[str]:
    """Extract bullet/numbered list items from a markdown content block."""
    items = []
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "+ ")):
            item = stripped[2:].strip()
            if item and not item.startswith("["):
                items.append(item)
        elif re.match(r"^\d+\.\s+", stripped):
            item = re.sub(r"^\d+\.\s+", "", stripped).strip()
            if item:
                items.append(item)
        if len(items) >= max_items:
            break
    return items


_WIKILINK_RE = re.compile(r"^\s*-?\s*\[\[.*?\]\]\s*$")


def _first_sentence_or_line(content: str) -> str:
    """Return first non-empty prose line, skipping headers, tables, and wiki-link lines."""
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith(("#", "|", "---", "```")):
            continue
        if _WIKILINK_RE.match(line):
            continue
        return line[:300]
    return ""


# ── Brain63 service ──────────────────────────────────────────────────────────

class Brain63Service:
    """
    Read-only knowledge retrieval from the Brain63 Obsidian vault.

    STRICTLY READ-ONLY — no file writes, creates, edits, or deletes, ever.
    """

    def __init__(self, vault_path: str) -> None:
        self.vault_path = Path(vault_path)
        self._index: list[ChunkResult] = []
        self._indexed_at: float = 0.0
        self._index_ttl: float = 300.0  # rebuild every 5 min

    # ── Index management ─────────────────────────────────────────────────────

    def _should_reindex(self) -> bool:
        return not self._index or (time.time() - self._indexed_at) > self._index_ttl

    def _ensure_index(self) -> None:
        if not self._should_reindex():
            return
        if not self.vault_path.exists():
            logger.warning("Brain63: vault not found at %s", self.vault_path)
            return
        chunks: list[ChunkResult] = []
        for md_file in self.vault_path.rglob("*.md"):
            if any(d in md_file.parts for d in _SKIP_DIRS):
                continue
            if md_file.name in _SKIP_FILES:
                continue
            try:
                chunks.extend(self._chunk_file(md_file))
            except Exception as exc:
                logger.debug("Brain63: skipped %s — %s", md_file.name, exc)
        self._index = chunks
        self._indexed_at = time.time()
        logger.info("Brain63: indexed %d chunks from vault", len(chunks))

    def _chunk_file(self, path: Path) -> list[ChunkResult]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        fm, body = _parse_frontmatter(text)
        rel = path.relative_to(self.vault_path)
        project = str(fm.get("project", "") or _infer_project(rel))
        note_type = str(fm.get("type", "") or _infer_type(path.name))
        rel_str = str(rel).replace("\\", "/")
        return [
            ChunkResult(
                file_path=rel_str,
                project=project,
                note_type=note_type,
                section=heading,
                content=content,
            )
            for heading, content in _split_by_headers(body)
            if content.strip()
        ]

    # ── Search ───────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        entity_hint: str = "",
        query_type: str = "general",
        top_k: int = 6,
    ) -> list[ChunkResult]:
        """
        Keyword-scored retrieval with entity + note-type boosts.
        READ-ONLY — no vault writes, ever.
        Returns top_k ChunkResult objects sorted by score descending.
        """
        self._ensure_index()
        if not self._index:
            return []

        query_tokens = _tokenize(query)
        # Normalise entity hint to Brain63 project name
        entity_key = entity_hint.lower().replace(" ", "").replace("-", "")
        project_name = _ENTITY_TO_PROJECT.get(entity_key, "") or _ENTITY_TO_PROJECT.get(
            entity_hint.lower().strip(), ""
        )
        if not project_name and entity_hint:
            project_name = entity_hint  # fallback: use as-is

        preferred_files = _TYPE_FILE_PRIORITY.get(query_type, [])

        scored: list[ChunkResult] = []
        for chunk in self._index:
            # Keyword overlap score
            chunk_tokens = _tokenize(
                chunk.content + " " + chunk.section + " " + chunk.project
            )
            overlap = query_tokens & chunk_tokens
            if not overlap and not entity_hint:
                continue
            base_score = len(overlap) / (len(chunk_tokens) ** 0.5 + 1)

            # Entity boost: matches on project folder name
            if project_name:
                proj_match = project_name.lower().replace(" ", "").replace("-", "")
                chunk_proj = chunk.project.lower().replace(" ", "").replace("-", "")
                chunk_path_flat = chunk.file_path.lower().replace(" ", "").replace("-", "")
                if proj_match and (proj_match in chunk_proj or proj_match in chunk_path_flat):
                    base_score = base_score * 3.0 + 1.0  # guarantee entity-matched chunks score

            # File-type boost
            if preferred_files:
                fname = chunk.file_path.split("/")[-1]
                if fname in preferred_files:
                    base_score *= 2.0

            # Section-title boost: known high-value sections by query type
            sec_lower = chunk.section.lower()
            if query_type == "overview" and sec_lower in (
                "what it is", "what is it", "overview", "about", "purpose", "description", "summary"
            ):
                base_score *= 2.5
            elif query_type == "status" and sec_lower in (
                "current phase", "current focus", "current state", "status", "phase",
                "blockers", "next actions", "next steps"
            ):
                base_score *= 2.5
            elif query_type == "decisions" and sec_lower in (
                "decisions", "confirmed decisions", "pending decisions", "resolved decisions",
                "architecture decisions", "design decisions"
            ):
                base_score *= 2.5

            # Note-type boosts
            if chunk.note_type in ("status", "decisions"):
                base_score *= 1.4
            elif chunk.note_type in ("overview", "architecture", "vision"):
                base_score *= 1.2

            if base_score > 0:
                c = ChunkResult(
                    file_path=chunk.file_path,
                    project=chunk.project,
                    note_type=chunk.note_type,
                    section=chunk.section,
                    content=chunk.content,
                    score=base_score,
                )
                scored.append(c)

        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:top_k]

    # ── Answer formatting (deterministic — no LLM) ───────────────────────────

    def answer_status(self, entity_name: str, chunks: list[ChunkResult]) -> Brain63Answer | None:
        """Format a concise status answer from the most relevant status chunks."""
        if not chunks:
            return None

        # Prefer Status.md chunks
        status_chunks = [c for c in chunks if "Status" in c.file_path or c.note_type == "status"]
        working = status_chunks or chunks

        phase = focus = blockers = next_actions = ""
        sources: list[str] = []

        for chunk in working:
            if chunk.file_path not in sources:
                sources.append(chunk.file_path)
            s = chunk.section.lower()
            content = chunk.content.strip()

            if not chunk.section:
                # Root section — scan for inline key-value lines
                for line in content.split("\n"):
                    ll = line.lower().strip()
                    if ll.startswith("current phase") and not phase:
                        phase = line.split(":", 1)[-1].strip() if ":" in line else content
                    elif ll.startswith("current focus") and not focus:
                        focus = line.split(":", 1)[-1].strip() if ":" in line else ""
            elif "current phase" in s and not phase:
                phase = _first_sentence_or_line(content)
            elif "current focus" in s and not focus:
                items = _bullet_items(content, 3)
                focus = "; ".join(items) if items else _first_sentence_or_line(content)
            elif "blocker" in s and not blockers:
                items = _bullet_items(content, 3)
                if items:
                    blockers = "; ".join(items)
                elif "none" in content.lower():
                    blockers = "None"
            elif "next action" in s and not next_actions:
                items = _bullet_items(content, 3)
                next_actions = "; ".join(items) if items else _first_sentence_or_line(content)

        if not any([phase, focus, blockers, next_actions]):
            # Fall back to the top chunk's content as-is
            top = working[0]
            summary = "\n".join(
                line for line in top.content.split("\n")
                if line.strip() and not line.startswith("|") and not line.startswith("---")
            )[:500]
            if not summary:
                return None
            confidence = "medium" if top.score >= 2.0 else "low"
            return Brain63Answer(
                text=f"According to Brain63 ({top.file_path}):\n{summary}",
                confidence=confidence,
                sources=sources[:2],
            )

        parts: list[str] = []
        if phase:
            parts.append(f"Phase: {phase}")
        if focus:
            parts.append(f"Focus: {focus}")
        if blockers:
            parts.append(f"Blockers: {blockers}")
        if next_actions:
            parts.append(f"Next: {next_actions}")

        top_score = chunks[0].score
        confidence = "high" if top_score >= 2.5 else "medium"
        source_label = sources[0] if sources else "Brain63"
        return Brain63Answer(
            text=f"According to Brain63 ({source_label}):\n" + "\n".join(parts),
            confidence=confidence,
            sources=sources[:2],
        )

    def answer_overview(self, entity_name: str, chunks: list[ChunkResult]) -> Brain63Answer | None:
        """Format an overview answer from overview/README chunks."""
        if not chunks:
            return None
        overview_chunks = [
            c for c in chunks
            if ("Overview" in c.file_path or c.note_type == "overview")
            and c.section.lower() not in ("links", "related", "see also", "index", "navigation")
        ]
        working = overview_chunks or [
            c for c in chunks
            if c.section.lower() not in ("links", "related", "see also", "index", "navigation")
        ]
        if not working:
            working = chunks

        # Prefer sections with prose content describing what the project is
        _PROSE_SECTIONS = {"what it is", "what is it", "overview", "about", "purpose", "description"}
        prose_first = [c for c in working if c.section.lower() in _PROSE_SECTIONS]
        if prose_first:
            working = prose_first + [c for c in working if c not in prose_first]

        sources = []
        paragraphs: list[str] = []
        for chunk in working:
            if len(paragraphs) >= 2:
                break
            if chunk.file_path not in sources:
                sources.append(chunk.file_path)
            line = _first_sentence_or_line(chunk.content)
            # Skip bullet-list first lines — overview should be prose, not feature lists
            if line and line not in paragraphs and not line.startswith(("- ", "* ", "+ ")):
                paragraphs.append(line)

        if not paragraphs:
            return None

        text = "\n".join(paragraphs[:2])
        top_score = chunks[0].score
        confidence = "high" if top_score >= 2.5 else "medium"
        source_label = sources[0] if sources else "Brain63"
        return Brain63Answer(
            text=f"According to Brain63 ({source_label}):\n{text}",
            confidence=confidence,
            sources=sources,
        )

    def answer_decisions(self, entity_name: str, chunks: list[ChunkResult]) -> Brain63Answer | None:
        """Format a decisions answer from decisions-type chunks."""
        if not chunks:
            return None
        dec_chunks = [c for c in chunks if "Decisions" in c.file_path or c.note_type in ("decisions", "decision_log")]
        working = dec_chunks or chunks

        sources = []
        entries: list[str] = []
        for chunk in working[:4]:
            if chunk.file_path not in sources:
                sources.append(chunk.file_path)
            content = chunk.content.strip()
            # Collect bullet entries or first paragraph
            items = _bullet_items(content, 4)
            if items:
                entries.extend(items)
            else:
                first = _first_sentence_or_line(content)
                if first:
                    entries.append(first)
            if len(entries) >= 5:
                break

        if not entries:
            return None

        top_score = chunks[0].score
        confidence = "high" if top_score >= 2.5 else "medium"
        source_label = sources[0] if sources else "Brain63"
        bullet_list = "\n".join(f"- {e}" for e in entries[:5])
        return Brain63Answer(
            text=f"According to Brain63 ({source_label}):\n{bullet_list}",
            confidence=confidence,
            sources=sources,
        )

    def answer_general(self, query: str, chunks: list[ChunkResult]) -> Brain63Answer | None:
        """Format a general answer from the top chunks."""
        if not chunks:
            return None

        sources = []
        content_parts: list[str] = []
        for chunk in chunks[:3]:
            if chunk.file_path not in sources:
                sources.append(chunk.file_path)
            line = _first_sentence_or_line(chunk.content)
            if line:
                content_parts.append(f"[{chunk.file_path}] {line}")

        if not content_parts:
            return None

        top_score = chunks[0].score
        confidence = "high" if top_score >= 3.0 else ("medium" if top_score >= 1.5 else "low")
        return Brain63Answer(
            text="According to Brain63:\n" + "\n".join(content_parts),
            confidence=confidence,
            sources=sources,
        )

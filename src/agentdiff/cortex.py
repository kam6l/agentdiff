"""Autonomous Skill Synthesis, Compressed Context Memory, and Multi-Agent Cortex.

This module provides the AgentDiff Cortex engine:
- SkillSynthesizer: Auto-generates reusable SKILL.md files from verified transactions.
- ContextCompressor: Compresses multi-file diffs and trajectories into dense semantic cards.
- AgentMemoryStore: Persistent repository trajectory memory and code fragility mapping.
- ContextPacker: Packages learned skills and constraints into optimal LLM prompts.
- SelfHealer: Emits machine-actionable remediation payloads for autonomous agent loops.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    clean = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[-\s]+", "-", clean).strip("-")
    return slug[:48] or "unnamed-skill"


@dataclass(frozen=True, slots=True)
class SkillContract:
    """A verified, reusable skill document synthesized from an agent transaction."""

    skill_id: str
    title: str
    task_intent: str
    triggers: list[str]
    hard_invariants: list[str]
    safe_paths: list[str]
    protected_paths: list[str]
    verification_recipe: str
    created_at: str = field(default_factory=_utc_now_iso)
    evidence_capsule_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        triggers_fmt = "\n".join(f"- `{t}`" for t in self.triggers) if self.triggers else "- `*`"
        invariants_fmt = "\n".join(f"- {inv}" for inv in self.hard_invariants) or "- None recorded."
        safe_fmt = "\n".join(f"- `{p}`" for p in self.safe_paths) or "- `*`"
        protected_fmt = "\n".join(f"- `{p}`" for p in self.protected_paths) or "- None."

        return f"""---
name: {self.skill_id}
title: "{self.title}"
created_at: "{self.created_at}"
capsule_id: "{self.evidence_capsule_id}"
---

# Skill: {self.title}

> **Task Intent**: {self.task_intent}

## When to Apply (Triggers)
{triggers_fmt}

## Hard Invariants & Learned Truths
{invariants_fmt}

## File Boundaries
### Safe Paths (Allowed Mutex)
{safe_fmt}

### Protected Paths (Strictly Preserve)
{protected_fmt}

## Verification Recipe
```bash
{self.verification_recipe}
```
"""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillContract:
        return cls(
            skill_id=str(data.get("skill_id", "skill")),
            title=str(data.get("title", "Learned Skill")),
            task_intent=str(data.get("task_intent", "")),
            triggers=list(data.get("triggers", [])),
            hard_invariants=list(data.get("hard_invariants", [])),
            safe_paths=list(data.get("safe_paths", [])),
            protected_paths=list(data.get("protected_paths", [])),
            verification_recipe=str(data.get("verification_recipe", "pytest")),
            created_at=str(data.get("created_at", _utc_now_iso())),
            evidence_capsule_id=str(data.get("evidence_capsule_id", "")),
        )


@dataclass(frozen=True, slots=True)
class CompressedContextCard:
    """Dense semantic summary of an execution trajectory for prompt context injection."""

    task: str
    run_id: str
    outcome: str
    blast_radius: int
    modified_symbols_or_files: list[str]
    key_learnings: list[str]
    timestamp: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_prompt_block(self) -> str:
        files_str = ", ".join(self.modified_symbols_or_files[:8])
        learnings_str = "; ".join(self.key_learnings[:3])
        return (
            f"• [Past Task: '{self.task}'] Result: {self.outcome} (Risk: {self.blast_radius}/100)\n"
            f"  Touched: {files_str}\n"
            f"  Learnings: {learnings_str}"
        )


class ContextCompressor:
    """Compresses verbose transaction manifests into dense semantic cards."""

    @staticmethod
    def compress_trajectory(
        task: str,
        run_id: str,
        mutations: dict[str, Any] | list[dict[str, Any]],
        policy_decision: str,
        blast_radius: int,
        argv: list[str] | tuple[str, ...] | None = None,
    ) -> CompressedContextCard:
        modified_files: list[str] = []
        key_learnings: list[str] = []

        if isinstance(mutations, dict):
            created = mutations.get("created", [])
            modified = mutations.get("modified", [])
            deleted = mutations.get("deleted", [])
            all_files = [
                f.get("path", str(f)) if isinstance(f, dict) else str(f)
                for f in (*created, *modified, *deleted)
            ]
            modified_files = all_files[:12]
        elif isinstance(mutations, list):
            for item in mutations:
                if isinstance(item, dict) and "path" in item:
                    modified_files.append(item["path"])
                elif isinstance(item, str):
                    modified_files.append(item)

        if policy_decision.lower() in {"allow", "pass", "clean"}:
            key_learnings.append(
                f"Clean transactional execution across {len(modified_files)} files"
            )
        else:
            key_learnings.append(f"Triggered policy review/denial (score: {blast_radius})")

        if argv:
            cmd_preview = " ".join(argv[:3])
            key_learnings.append(f"Executed via `{cmd_preview}`")

        return CompressedContextCard(
            task=task or "Unspecified Task",
            run_id=run_id,
            outcome=policy_decision.upper(),
            blast_radius=blast_radius,
            modified_symbols_or_files=modified_files,
            key_learnings=key_learnings,
        )


class SkillSynthesizer:
    """Extracts architectural invariants from verified runs and synthesizes SKILL.md files."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root).resolve() if root else Path.cwd()
        self.skills_dir = self.root / ".agentdiff" / "skills"

    def synthesize(
        self,
        capsule_data: dict[str, Any],
        title: str | None = None,
        save: bool = True,
    ) -> SkillContract:
        run_id = str(capsule_data.get("run_id", "run"))
        task_intent = str(
            capsule_data.get("task", "")
            or capsule_data.get("metadata", {}).get("task", "")
            or f"Task {run_id}"
        )

        slug_title = title or task_intent
        skill_id = _slugify(slug_title)
        skill_title = title or slug_title.capitalize()

        mutations = capsule_data.get("mutations", {})
        created = mutations.get("created", [])
        modified = mutations.get("modified", [])

        safe_paths: list[str] = []
        for item in (*created, *modified):
            path = item.get("path", "") if isinstance(item, dict) else str(item)
            if path:
                safe_paths.append(path)

        protected_paths: list[str] = [
            ".env*",
            "*.pem",
            "*.key",
            ".github/workflows/**",
        ]

        words = [
            w.lower()
            for w in re.findall(r"\w{3,}", task_intent)
            if w.lower() not in {"the", "and", "for", "with", "this"}
        ]
        triggers = words[:6] if words else [skill_id]

        first_safe = f"`{safe_paths[0]}`" if safe_paths else "core entry points"
        invariants = [
            f"Preserve existing functionality in {first_safe}.",
            "Never commit raw API keys, secrets, or temporary logs.",
            "All unit and integration tests must pass cleanly before transaction completion.",
        ]

        argv = capsule_data.get("argv", [])
        recipe = "pytest"
        if any("pytest" in str(arg) for arg in argv):
            recipe = "pytest"
        elif (self.root / "package.json").exists():
            recipe = "npm test"
        elif (self.root / "Cargo.toml").exists():
            recipe = "cargo test"

        contract = SkillContract(
            skill_id=skill_id,
            title=skill_title,
            task_intent=task_intent,
            triggers=triggers,
            hard_invariants=invariants,
            safe_paths=safe_paths,
            protected_paths=protected_paths,
            verification_recipe=recipe,
            evidence_capsule_id=run_id,
        )

        if save:
            self.save_skill(contract)

        return contract

    def save_skill(self, skill: SkillContract) -> Path:
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.skills_dir / f"{skill.skill_id}.md"
        file_path.write_text(skill.to_markdown(), encoding="utf-8")
        return file_path

    def list_skills(self) -> list[SkillContract]:
        if not self.skills_dir.exists():
            return []
        skills: list[SkillContract] = []
        for file in sorted(self.skills_dir.glob("*.md")):
            try:
                content = file.read_text(encoding="utf-8")
                title_match = re.search(r'title:\s*"([^"]+)"', content)
                title = title_match.group(1) if title_match else file.stem
                intent_match = re.search(r">\s*\*\*Task Intent\*\*:\s*([^\n]+)", content)
                intent = intent_match.group(1) if intent_match else ""
                skills.append(
                    SkillContract(
                        skill_id=file.stem,
                        title=title,
                        task_intent=intent,
                        triggers=[file.stem],
                        hard_invariants=[],
                        safe_paths=[],
                        protected_paths=[],
                        verification_recipe="pytest",
                        evidence_capsule_id="",
                    )
                )
            except OSError:
                continue
        return skills


class AgentMemoryStore:
    """Persistent repository-level memory store for trajectories, skills, and code fragility."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root).resolve() if root else Path.cwd()
        self.memory_dir = self.root / ".agentdiff"
        self.memory_file = self.memory_dir / "memory.json"

    def _load_raw(self) -> dict[str, Any]:
        if not self.memory_file.exists():
            return {
                "version": 1,
                "episodes": [],
                "fragile_paths": {},
                "model_stats": {},
                "updated_at": _utc_now_iso(),
            }
        try:
            return json.loads(self.memory_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "version": 1,
                "episodes": [],
                "fragile_paths": {},
                "model_stats": {},
                "updated_at": _utc_now_iso(),
            }

    def _save_raw(self, data: dict[str, Any]) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        data["updated_at"] = _utc_now_iso()
        self.memory_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def record_episode(
        self,
        card: CompressedContextCard,
        collateral_paths: list[str] | None = None,
        model_name: str = "default",
    ) -> None:
        data = self._load_raw()
        data["episodes"].append(card.to_dict())

        fragile = data.setdefault("fragile_paths", {})
        if collateral_paths:
            for p in collateral_paths:
                fragile[p] = round(fragile.get(p, 0.0) + 1.0, 2)

        stats = data.setdefault("model_stats", {})
        m_stat = stats.setdefault(
            model_name,
            {"total_runs": 0, "clean_runs": 0, "avg_blast_radius": 0.0},
        )
        total = m_stat["total_runs"] + 1
        is_clean = 1 if card.outcome == "ALLOW" else 0
        clean = m_stat["clean_runs"] + is_clean
        prior = m_stat["avg_blast_radius"] * m_stat["total_runs"]
        avg_score = round((prior + card.blast_radius) / total, 1)

        m_stat["total_runs"] = total
        m_stat["clean_runs"] = clean
        m_stat["avg_blast_radius"] = avg_score

        self._save_raw(data)

    def get_stats(self) -> dict[str, Any]:
        data = self._load_raw()
        episodes = data.get("episodes", [])
        return {
            "total_episodes": len(episodes),
            "fragile_paths_tracked": len(data.get("fragile_paths", {})),
            "models_benchmarked": list(data.get("model_stats", {}).keys()),
            "model_stats": data.get("model_stats", {}),
            "top_fragile_paths": sorted(
                data.get("fragile_paths", {}).items(), key=lambda x: x[1], reverse=True
            )[:5],
        }


class ContextPacker:
    """Assembles learned skills and memory into a dense, optimal LLM context block."""

    @staticmethod
    def pack(task_prompt: str, root: Path | str | None = None) -> str:
        root_path = Path(root).resolve() if root else Path.cwd()
        synthesizer = SkillSynthesizer(root_path)
        memory = AgentMemoryStore(root_path)

        skills = synthesizer.list_skills()
        stats = memory.get_stats()
        top_fragile = stats.get("top_fragile_paths", [])

        task_words = set(re.findall(r"\w{3,}", task_prompt.lower()))
        matched_skills: list[SkillContract] = []
        for s in skills:
            by_words = any(w in task_words for w in s.triggers)
            by_sub = any(t.lower() in task_prompt.lower() for t in s.triggers)
            if by_words or by_sub:
                matched_skills.append(s)

        if not matched_skills and skills:
            matched_skills = skills[:2]

        skills_block = ""
        if matched_skills:
            entries = [
                f"- **{s.title}**: {s.task_intent} (Verify with `{s.verification_recipe}`)"
                for s in matched_skills
            ]
            skills_block = "\n### RELEVANT ARCHITECTURAL SKILLS:\n" + "\n".join(entries)

        fragile_block = ""
        if top_fragile:
            f_entries = [f"- `{path}` (Risk frequency: {score})" for path, score in top_fragile]
            fragile_block = (
                "\n### FRAGILE PATHS (Historically high collateral risk):\n" + "\n".join(f_entries)
            )

        return f"""<!-- AGENTDIFF CONTEXT MEMORY PACK -->
## AgentDiff Execution Directives
**Target Task Intent**: {task_prompt}
{skills_block}
{fragile_block}

### Safety Mandate:
1. Stay strictly within the scope of `{task_prompt}`.
2. Do not introduce collateral modifications to untouched modules.
3. Validate state before completion.
<!-- END CONTEXT PACK -->"""


class SelfHealer:
    """Generates machine-actionable repair payloads for autonomous agent retry loops."""

    @staticmethod
    def generate_remediation(capsule_data: dict[str, Any]) -> dict[str, Any]:
        run_id = str(capsule_data.get("run_id", "unknown"))
        decision = str(capsule_data.get("policy_decision", "DENY"))
        br = capsule_data.get("blast_radius", 0)
        score = int(br.get("score", 0) if isinstance(br, dict) else br)

        mutations = capsule_data.get("mutations", {})
        modified = mutations.get("modified", [])
        created = mutations.get("created", [])
        deleted = mutations.get("deleted", [])

        collateral_files: list[str] = []
        for item in (*modified, *created, *deleted):
            path = item.get("path", "") if isinstance(item, dict) else str(item)
            decision_item = item.get("decision", "") if isinstance(item, dict) else ""
            if decision_item in {"review", "deny"} or "protected" in str(item).lower():
                collateral_files.append(path)

        if not collateral_files and modified:
            collateral_files = [
                m.get("path", str(m)) if isinstance(m, dict) else str(m) for m in modified[:3]
            ]

        remediation_needed = decision.upper() != "ALLOW" or score >= 50
        task_label = str(capsule_data.get("task", "task"))

        if remediation_needed:
            prompt_fix = (
                f"Your previous attempt on '{task_label}' triggered a {decision} verdict "
                f"with blast-radius {score}/100. Revert collateral in {collateral_files}."
            )
        else:
            prompt_fix = "No remediation needed. Transaction clean."

        return {
            "run_id": run_id,
            "status": "REMEDIATION_REQUIRED" if remediation_needed else "CLEAN",
            "decision": decision,
            "blast_radius_score": score,
            "collateral_files_to_revert": collateral_files,
            "recovery_command": f"agentdiff rollback {run_id} --safe-only",
            "prompt_repair_directive": prompt_fix,
        }

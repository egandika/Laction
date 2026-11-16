"""
Skill Manager — procedural memory ala Hermes.

Skill = folder berisi `SKILL.md` (Markdown + frontmatter YAML sederhana,
mengikuti konvensi agentskills.io). Ada tiga sumber skill:

1. `laction_agent/skills/bundled/*` — skill bawaan yang ikut ter-package.
2. `./skills/*` — skill milik repo (opsional, mudah diedit user).
3. `$LACTION_HOME/skills/*` — skill yang ditulis agent sendiri (self-improving).

Skill buatan agent menimpa skill dengan nama sama dari sumber lain.
"""
from __future__ import annotations

import re
from pathlib import Path

_PKG_BUNDLED = Path(__file__).resolve().parent / "bundled"
_REPO_SKILLS = Path("skills")


class SkillManager:
    def __init__(self, home: Path, bundled_dirs: list[Path] | None = None):
        self.home = Path(home)
        self.skills_dir = self.home / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.bundled_dirs = [Path(p) for p in (bundled_dirs or [_PKG_BUNDLED, _REPO_SKILLS])]

    def _bases(self) -> list[Path]:
        # Urutan pencarian: buatan agent -> repo -> package bawaan.
        return [self.skills_dir, *self.bundled_dirs]

    def _all_dirs(self) -> list[Path]:
        dirs: list[Path] = []
        for base in self._bases():
            if base.exists():
                dirs += [d for d in base.iterdir() if d.is_dir()]
        return dirs

    def list_skills(self) -> list[dict]:
        found: dict[str, dict] = {}
        for d in self._all_dirs():
            skill_file = d / "SKILL.md"
            if not skill_file.exists():
                continue
            text = skill_file.read_text(encoding="utf-8")
            found.setdefault(
                d.name,
                {"name": d.name, "description": _extract_description(text), "path": str(skill_file)},
            )
        return sorted(found.values(), key=lambda x: x["name"])

    def view_skill(self, name: str) -> str | None:
        for base in self._bases():
            f = base / name / "SKILL.md"
            if f.exists():
                return f.read_text(encoding="utf-8")
        return None

    def create_skill(self, name: str, content: str) -> str:
        name = re.sub(r"[^a-z0-9\-]+", "-", name.lower()).strip("-")
        if not name:
            raise ValueError("Nama skill tidak valid.")
        folder = self.skills_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        skill_file = folder / "SKILL.md"
        body = content.strip()
        if not body.startswith("---"):
            first_line = body.splitlines()[0][:80] if body else name
            body = f"---\nname: {name}\ndescription: {first_line}\n---\n\n{body}\n"
        skill_file.write_text(body, encoding="utf-8")
        return str(skill_file)

    def delete_skill(self, name: str) -> bool:
        folder = self.skills_dir / name
        skill_file = folder / "SKILL.md"
        if not skill_file.exists():
            return False
        skill_file.unlink()
        try:
            folder.rmdir()
        except OSError:
            pass
        return True


def _extract_description(text: str) -> str:
    m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    lines = [
        l.strip() for l in text.splitlines()
        if l.strip() and not l.startswith(("#", "-", "---", "name:"))
    ]
    return lines[0][:80] if lines else ""

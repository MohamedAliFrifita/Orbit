"""
Chargement des prompts versionnes (voir orbit-coding-guide.md §6 et charte-ai-commandos.md §3).

Les prompts ne sont jamais des f-strings inline dans le code metier -
ils vivent dans orbit/prompts/{role}/v{N}.md.
"""

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


def load_prompt(role: str, version: str = "v1") -> str:
    path = PROMPTS_DIR / role / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt introuvable: {path}. Voir orbit-coding-guide.md §6 pour la convention."
        )
    return path.read_text(encoding="utf-8")

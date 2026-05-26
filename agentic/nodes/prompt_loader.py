"""
Prompt loader utility for loading prompt templates from text files
"""
from pathlib import Path
from jinja2 import Template


class PromptLoader:
    """Load and cache prompt templates from text files"""

    _cache = {}

    @classmethod
    def load(cls, name: str) -> Template:
        """
        Load a prompt template by name

        Args:
            name: Prompt name (e.g., 'writer', 'seo', 'editor')
                 Corresponds to prompts/{name}.txt

        Returns:
            Jinja2 Template object ready for rendering

        Example:
            template = PromptLoader.load("writer")
            prompt = template.render(topic="AI", tone="friendly", ...)
        """
        if name not in cls._cache:
            path = Path(__file__).parent.parent / "prompts" / f"{name}.txt"
            if not path.exists():
                raise FileNotFoundError(f"Prompt template not found: {path}")
            cls._cache[name] = Template(path.read_text())
        return cls._cache[name]

    @classmethod
    def clear_cache(cls):
        """Clear the template cache (useful for testing)"""
        cls._cache = {}

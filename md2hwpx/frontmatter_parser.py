"""
YAML front matter parser using python-frontmatter.
"""

import frontmatter


def parse_markdown_with_frontmatter(file_path: str) -> tuple[dict, str]:
    """
    Parse a Markdown file with YAML front matter.

    Args:
        file_path: Path to the Markdown file

    Returns:
        (metadata_dict, markdown_content_without_frontmatter)
    """
    post = frontmatter.load(file_path)
    return dict(post.metadata), post.content


def parse_markdown_string_with_frontmatter(markdown_text: str) -> tuple[dict, str]:
    """
    Parse a Markdown string with YAML front matter.

    Args:
        markdown_text: Markdown content as string

    Returns:
        (metadata_dict, markdown_content_without_frontmatter)
    """
    post = frontmatter.loads(markdown_text)
    return dict(post.metadata), post.content


def convert_metadata_to_pandoc_meta(metadata: dict) -> dict:
    """
    Convert front matter metadata to Pandoc meta format.

    Input:  {"title": "Doc Title", "author": "Name", "date": "2025-01-01"}
    Output: {"title": {"t": "MetaInlines", "c": [{"t": "Str", "c": "Doc"}, {"t": "Space"}, {"t": "Str", "c": "Title"}]}, ...}

    Args:
        metadata: Dictionary of metadata from front matter

    Returns:
        Pandoc-compatible meta dictionary
    """
    pandoc_meta = {}

    for key, value in metadata.items():
        if isinstance(value, str):
            # Simple string -> MetaInlines (split by spaces)
            inlines = _text_to_inlines(value)
            pandoc_meta[key] = {
                "t": "MetaInlines",
                "c": inlines
            }
        elif isinstance(value, list):
            # List -> MetaList
            items = []
            for v in value:
                inlines = _text_to_inlines(str(v))
                items.append({
                    "t": "MetaInlines",
                    "c": inlines
                })
            pandoc_meta[key] = {
                "t": "MetaList",
                "c": items
            }
        elif isinstance(value, dict):
            # Dict -> MetaMap (recursive)
            pandoc_meta[key] = {
                "t": "MetaMap",
                "c": convert_metadata_to_pandoc_meta(value)
            }
        elif isinstance(value, bool):
            # Boolean -> MetaBool
            pandoc_meta[key] = {
                "t": "MetaBool",
                "c": value
            }
        elif isinstance(value, (int, float)):
            # Number -> MetaInlines (as string)
            pandoc_meta[key] = {
                "t": "MetaInlines",
                "c": [{"t": "Str", "c": str(value)}]
            }
        else:
            # Fallback: convert to string
            inlines = _text_to_inlines(str(value))
            pandoc_meta[key] = {
                "t": "MetaInlines",
                "c": inlines
            }

    return pandoc_meta


def _text_to_inlines(text: str) -> list:
    """
    Convert a text string to Pandoc inline elements (Str and Space).

    Args:
        text: Plain text string

    Returns:
        List of Pandoc inline elements
    """
    if not text:
        return []

    result = []
    words = text.split(' ')

    for i, word in enumerate(words):
        if word:
            result.append({"t": "Str", "c": word})
        if i < len(words) - 1:
            result.append({"t": "Space"})

    return result

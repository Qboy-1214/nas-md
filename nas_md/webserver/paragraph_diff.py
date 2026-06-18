"""Paragraph-level diff engine for real-time collaborative editing."""

from difflib import SequenceMatcher


def split_paragraphs(text: str) -> list[str]:
    """Split text by double newline (paragraph boundary)."""
    paragraphs = text.split('\n\n')
    while paragraphs and paragraphs[-1].strip() == '':
        paragraphs.pop()
    return paragraphs


def compute_diff(old_text: str, new_text: str) -> list[dict]:
    """Compute paragraph-level diff between old and new text.

    Returns list of changes:
    - {"type": "replace", "paraIdx": int, "content": str}
    - {"type": "insert", "paraIdx": int, "content": str}
    - {"type": "delete", "paraIdx": int}

    paraIdx: 0-indexed paragraph position.
    For insert: insert BEFORE the paragraph at paraIdx.
    For replace/delete: target the paragraph at paraIdx.
    """
    old_paras = split_paragraphs(old_text)
    new_paras = split_paragraphs(new_text)

    if old_paras == new_paras:
        return []

    sm = SequenceMatcher(None, old_paras, new_paras, autojunk=False)
    changes = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'replace':
            # Handle potentially unequal length replacements
            old_len = i2 - i1
            new_len = j2 - j1
            paired = min(old_len, new_len)

            for k in range(paired):
                changes.append({
                    'type': 'replace',
                    'paraIdx': i1 + k,
                    'content': new_paras[j1 + k],
                })

            if old_len > new_len:
                # More old paragraphs than new -> extras are deletions
                for k in range(paired, old_len):
                    changes.append({
                        'type': 'delete',
                        'paraIdx': i1 + k,
                    })
            elif new_len > old_len:
                # More new paragraphs than old -> extras are insertions
                for k in range(paired, new_len):
                    changes.append({
                        'type': 'insert',
                        'paraIdx': i2,
                        'content': new_paras[j1 + k],
                    })
        elif tag == 'delete':
            for i in range(i1, i2):
                changes.append({'type': 'delete', 'paraIdx': i})
        elif tag == 'insert':
            for j in range(j1, j2):
                changes.append({'type': 'insert', 'paraIdx': i1, 'content': new_paras[j]})

    return changes

import re
from typing import overload

import jmespath
from anyascii import anyascii
from jmespath import Options, functions
from pydantic import BaseModel

_BARE_NUMBER = re.compile(r"(==|!=|>=|<=|>|<)\s*(\d+(?:\.\d+)?)\b(?!`)")
_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _normalize(text: str) -> str:
    return _NON_ALNUM.sub("", anyascii(text).lower())


def _quote_numbers(expr: str) -> str:
    """Wrap bare numeric literals in JMESPath backticks so `x==100` becomes `x==`100``."""
    return _BARE_NUMBER.sub(r"\1`\2`", expr)


class CustomFunctions(functions.Functions):
    @functions.signature({"types": ["object"]}, {"types": ["string"]})
    def _func_search(self, obj, needle):
        """Normalized search across all string fields (handles Cyrillic, dots, etc.)."""
        needle_norm = _normalize(needle)
        for v in obj.values():
            if isinstance(v, str) and needle_norm in _normalize(v):
                return True
        return False


def apply_query[T: BaseModel](
    items: list[T],
    filter_expr: str | None = None,
    sort_by: str | None = None,
    limit: int | None = None,
) -> list[T]:
    """Apply JMESPath filter, sorting, and limit. Returns original models."""
    if not items:
        return items

    data = [item.model_dump() for item in items]
    key_field = "index" if data and "index" in data[0] else "id"
    key_to_item = {getattr(item, key_field): item for item in items}

    if filter_expr:
        filter_expr = _quote_numbers(filter_expr)
        expr = filter_expr if filter_expr.startswith("[") else f"[?{filter_expr}]"
        opts = Options(custom_functions=CustomFunctions())
        data = jmespath.search(expr, data, options=opts) or []

    if sort_by:
        desc = sort_by.startswith("-")
        key = sort_by.lstrip("-")
        data = sorted(data, key=lambda x: x.get(key, 0), reverse=desc)

    if limit and limit > 0:
        data = data[:limit]

    return [key_to_item[d[key_field]] for d in data]


@overload
def project[T: BaseModel](items: list[T], fields: None = None) -> list[T]: ...
@overload
def project[T: BaseModel](items: list[T], fields: list[str]) -> list[dict]: ...

def project[T: BaseModel](
    items: list[T],
    fields: list[str] | None = None,
) -> list[T] | list[dict]:
    if not fields:
        return items

    if not items:
        return []

    sample = items[0].model_dump()
    key_field = "index" if "index" in sample else "id"
    include = set(fields) | {key_field}
    return [item.model_dump(include=include) for item in items]


def _tsv_from_rows(keys: list[str], rows: list[dict]) -> str:
    lines = ['\t'.join(keys)]
    for row in rows:
        lines.append('\t'.join(str(row[k]) for k in keys))
    return '\n'.join(lines)


def to_tsv(items: list[BaseModel] | list[dict]) -> str:
    if not items:
        return ""
    first = items[0]
    if isinstance(first, BaseModel):
        keys = list(first.model_fields.keys())
        return _tsv_from_rows(keys, [item.model_dump() for item in items])  # type: ignore[union-attr]
    keys = list(first.keys())
    return _tsv_from_rows(keys, items)  # type: ignore[arg-type]

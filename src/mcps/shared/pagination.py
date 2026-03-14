from pydantic import BaseModel

DEFAULT_LIMIT = 50


class TsvList(BaseModel):
    data: str
    total: int
    offset: int
    has_more: bool


def paginate[T](items: list[T], limit: int = DEFAULT_LIMIT, offset: int = 0) -> tuple[list[T], int, bool]:
    """Apply pagination. Returns (paginated_items, total, has_more)."""
    total = len(items)
    paginated = items[offset : offset + limit]
    has_more = offset + limit < total
    return paginated, total, has_more

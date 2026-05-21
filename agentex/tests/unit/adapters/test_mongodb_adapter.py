"""Unit tests for the generic MongoDB CRUD adapter.

These tests exercise the adapter directly against a real MongoDB
(via the testcontainers `mongodb_database` fixture, which yields an
`AsyncDatabase` from pymongo's native async API). The focus is the
code paths touched by the motor → pymongo-async migration:

  - direct collection ops: insert_one / insert_many / find_one /
    update_one / delete_one / delete_many
  - cursor materialization via `await cursor.to_list(length=None)` for
    list(), find_by_field(), find_by_field_with_cursor()
  - timestamp + id round-tripping
"""

from datetime import datetime
from typing import Any

import pytest
from pydantic import BaseModel
from src.adapters.crud_store.adapter_mongodb import MongoDBCRUDRepository
from src.adapters.crud_store.exceptions import ItemDoesNotExist


def _naive(dt: datetime) -> datetime:
    """Strip tzinfo so we can compare adapter-supplied (tz-aware) vs
    Mongo-roundtripped (tz-naive UTC) timestamps without TypeErrors."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


class _Item(BaseModel):
    id: str | None = None
    name: str
    group: str | None = None
    payload: dict[str, Any] | None = None
    created_at: Any | None = None
    updated_at: Any | None = None


def _make_repo(mongodb_database) -> MongoDBCRUDRepository[_Item]:
    return MongoDBCRUDRepository(
        db=mongodb_database, collection_name="items", model_class=_Item
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_get_update_delete_roundtrip(mongodb_database):
    repo = _make_repo(mongodb_database)

    created = await repo.create(_Item(name="alpha", group="g1"))
    assert created.id is not None
    assert created.created_at is not None
    assert created.updated_at is not None

    fetched = await repo.get(id=created.id)
    assert fetched is not None
    assert fetched.name == "alpha"
    assert fetched.group == "g1"

    fetched.name = "alpha-renamed"
    updated = await repo.update(fetched)
    assert updated.name == "alpha-renamed"
    assert _naive(updated.updated_at) >= _naive(created.updated_at)

    await repo.delete(id=created.id)
    with pytest.raises(ItemDoesNotExist):
        await repo.get(id=created.id)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_batch_create_and_batch_get(mongodb_database):
    repo = _make_repo(mongodb_database)

    items = [_Item(name=f"b{i}", group="batch") for i in range(5)]
    created = await repo.batch_create(items)
    ids = [c.id for c in created]
    assert len(ids) == 5
    assert all(ids)

    fetched = await repo.batch_get(ids=ids)
    assert {f.name for f in fetched} == {"b0", "b1", "b2", "b3", "b4"}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_list_pagination_and_ordering(mongodb_database):
    repo = _make_repo(mongodb_database)

    await repo.batch_create(
        [_Item(name=f"item-{i:02d}", group="list") for i in range(15)]
    )

    page1 = await repo.list(
        filters={"group": "list"}, limit=5, page_number=1, order_by="name"
    )
    page2 = await repo.list(
        filters={"group": "list"}, limit=5, page_number=2, order_by="name"
    )
    page3 = await repo.list(
        filters={"group": "list"}, limit=5, page_number=3, order_by="name"
    )

    assert [i.name for i in page1] == [f"item-{n:02d}" for n in range(0, 5)]
    assert [i.name for i in page2] == [f"item-{n:02d}" for n in range(5, 10)]
    assert [i.name for i in page3] == [f"item-{n:02d}" for n in range(10, 15)]

    page1_desc = await repo.list(
        filters={"group": "list"},
        limit=5,
        page_number=1,
        order_by="name",
        order_direction="desc",
    )
    assert [i.name for i in page1_desc] == [f"item-{n:02d}" for n in range(14, 9, -1)]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_find_by_field_filters_and_limit(mongodb_database):
    repo = _make_repo(mongodb_database)

    await repo.batch_create(
        [_Item(name=f"f{i}", group="A" if i % 2 == 0 else "B") for i in range(10)]
    )

    group_a = await repo.find_by_field("group", "A", limit=10)
    group_b = await repo.find_by_field("group", "B", limit=10)
    assert len(group_a) == 5
    assert len(group_b) == 5
    assert all(item.group == "A" for item in group_a)
    assert all(item.group == "B" for item in group_b)

    page1 = await repo.find_by_field("group", "A", limit=2, page_number=1)
    page2 = await repo.find_by_field("group", "A", limit=2, page_number=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert {p.id for p in page1}.isdisjoint({p.id for p in page2})


@pytest.mark.asyncio
@pytest.mark.unit
async def test_find_by_field_with_cursor_before_after(mongodb_database):
    repo = _make_repo(mongodb_database)

    created = await repo.batch_create(
        [_Item(name=f"c{i}", group="cursor") for i in range(8)]
    )
    middle_id = created[4].id

    after = await repo.find_by_field_with_cursor(
        "group", "cursor", limit=10, after_id=middle_id
    )
    before = await repo.find_by_field_with_cursor(
        "group", "cursor", limit=10, before_id=middle_id
    )

    assert middle_id not in {i.id for i in after}
    assert middle_id not in {i.id for i in before}
    # Every result is from the same group
    assert all(i.group == "cursor" for i in after + before)
    # Combined coverage minus the cursor doc equals the rest of the set
    assert {i.id for i in after} | {i.id for i in before} == {
        i.id for i in created if i.id != middle_id
    }


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_by_field(mongodb_database):
    repo = _make_repo(mongodb_database)

    await repo.batch_create([_Item(name=f"d{i}", group="del") for i in range(6)])

    deleted = await repo.delete_by_field("group", "del")
    assert deleted == 6

    with pytest.raises(ItemDoesNotExist):
        await repo.batch_get(names=[f"d{i}" for i in range(6)])

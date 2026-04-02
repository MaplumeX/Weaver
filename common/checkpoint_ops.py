import asyncio
from typing import Any


def _list_checkpoints_sync(
    checkpointer: Any,
    config: dict[str, Any] | None,
    *,
    filter: dict[str, Any] | None = None,
    before: dict[str, Any] | None = None,
    limit: int | None = None,
) -> list[Any]:
    return list(checkpointer.list(config, filter=filter, before=before, limit=limit))


async def aget_checkpoint_tuple(checkpointer: Any, config: dict[str, Any]) -> Any:
    if checkpointer is None:
        return None
    if hasattr(checkpointer, "aget_tuple"):
        return await checkpointer.aget_tuple(config)
    if hasattr(checkpointer, "get_tuple"):
        return await asyncio.to_thread(checkpointer.get_tuple, config)
    raise AttributeError("Checkpointer does not support get_tuple/aget_tuple")


async def alist_checkpoints(
    checkpointer: Any,
    config: dict[str, Any] | None,
    *,
    filter: dict[str, Any] | None = None,
    before: dict[str, Any] | None = None,
    limit: int | None = None,
) -> list[Any]:
    if checkpointer is None:
        return []
    if hasattr(checkpointer, "alist"):
        return [
            item
            async for item in checkpointer.alist(
                config,
                filter=filter,
                before=before,
                limit=limit,
            )
        ]
    if hasattr(checkpointer, "list"):
        return await asyncio.to_thread(
            _list_checkpoints_sync,
            checkpointer,
            config,
            filter=filter,
            before=before,
            limit=limit,
        )
    raise AttributeError("Checkpointer does not support list/alist")


async def adelete_checkpoint(checkpointer: Any, config: dict[str, Any]) -> bool:
    if checkpointer is None:
        return False
    if hasattr(checkpointer, "adelete"):
        await checkpointer.adelete(config)
        return True
    if hasattr(checkpointer, "delete"):
        await asyncio.to_thread(checkpointer.delete, config)
        return True
    return False

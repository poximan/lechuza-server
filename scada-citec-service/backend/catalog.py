import asyncio
from dataclasses import dataclass
from typing import Dict, List

from . import config


@dataclass(frozen=True)
class ElementDescriptor:
    tag: str
    label: str
    voltage: str
    group_prefix: str
    group_label: str


@dataclass(frozen=True)
class GroupDescriptor:
    prefix: str
    label: str
    elements: List[ElementDescriptor]


class MimicCatalog:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._groups: List[GroupDescriptor] = []
        self._flat: List[ElementDescriptor] = []

    async def update_from_tags(self, tags: List[str]) -> None:
        new_groups = self._build_groups(tags)
        flat = [element for group in new_groups for element in group.elements]
        async with self._lock:
            self._groups = new_groups
            self._flat = flat

    async def groups(self) -> List[GroupDescriptor]:
        async with self._lock:
            return [group for group in self._groups]

    async def elements(self) -> List[ElementDescriptor]:
        async with self._lock:
            return [element for element in self._flat]

    def _build_groups(self, tags: List[str]) -> List[GroupDescriptor]:
        grouped: Dict[str, List[str]] = {}
        for tag in tags:
            if not tag:
                continue
            prefix = tag.split("_", 1)[0].upper()
            grouped.setdefault(prefix, []).append(tag)
        group_descriptors: List[GroupDescriptor] = []
        for prefix in sorted(grouped.keys()):
            names = sorted(grouped[prefix], key=str.lower)
            elements = [
                ElementDescriptor(
                    tag=name,
                    label=name,
                    voltage=config._voltage_from_tag(name),
                    group_prefix=prefix,
                    group_label=config.station_label_for(prefix),
                )
                for name in names
            ]
            group_descriptors.append(
                GroupDescriptor(
                    prefix=prefix,
                    label=config.station_label_for(prefix),
                    elements=elements,
                )
            )
        return group_descriptors

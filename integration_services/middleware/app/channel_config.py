from typing import Any

from pydantic import BaseModel


class FieldMapping(BaseModel):
    path: str

class InventoryEndpoint(BaseModel):
    method: str = "PUT"
    url: str
    body_template: dict[str, str]

class ChannelConfig(BaseModel):
    platform: str
    field_mappings: dict[str, str]
    items_root: str
    item_mappings: dict[str, str]
    orders_endpoint: str | None = None
    inventory_endpoint: InventoryEndpoint | None = None


class ConfigStore:
    def __init__(self) -> None:
        self._configs: dict[str, ChannelConfig] = {}

    def load_defaults(self, defaults: dict[str, dict]) -> None:
        for platform, data in defaults.items():
            if platform not in self._configs:
                self._configs[platform] = ChannelConfig(**data)

    def get(self, platform: str) -> ChannelConfig | None:
        return self._configs.get(platform)

    def list(self) -> list[ChannelConfig]:
        return list(self._configs.values())

    def create(self, config: ChannelConfig) -> ChannelConfig:
        if config.platform in self._configs:
            raise ValueError(f"Config for platform '{config.platform}' already exists.")
        self._configs[config.platform] = config
        return config

    def update(self, platform: str, config: ChannelConfig) -> ChannelConfig:
        if platform not in self._configs:
            raise ValueError(f"Config for platform '{platform}' not found.")
        self._configs[platform] = config
        return config

    def delete(self, platform: str) -> None:
        if platform not in self._configs:
            raise ValueError(f"Config for platform '{platform}' not found.")
        del self._configs[platform]


config_store = ConfigStore()

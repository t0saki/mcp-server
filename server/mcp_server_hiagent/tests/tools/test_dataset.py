from __future__ import annotations

from typing import Any

import pytest

from mcp_server_hiagent.versions.v3_1_0.tools.dataset import get_dataset, list_datasets


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call(self, **kwargs: Any) -> dict[str, object]:
        self.calls.append(kwargs)
        return {"ResponseMetadata": {"Action": kwargs["action"]}, "Result": {}}


def test_list_datasets_builds_workspace_request() -> None:
    client = RecordingClient()

    list_datasets(client, workspace_id="ws-1", page_number=2, page_size=10)

    assert client.calls[0] == {
        "action": "ListDatasets",
        "version": "2023-08-01",
        "service": "app",
        "body": {
            "WorkspaceID": "ws-1",
            "ListOpt": {"PageNumber": 2, "PageSize": 10},
        },
    }


def test_list_datasets_defaults() -> None:
    client = RecordingClient()

    list_datasets(client, workspace_id="ws-1")

    assert client.calls[0]["body"]["ListOpt"] == {"PageNumber": 1, "PageSize": 20}


def test_list_datasets_requires_workspace() -> None:
    with pytest.raises(ValueError):
        list_datasets(RecordingClient(), workspace_id="")


@pytest.mark.parametrize(
    "page_number,page_size",
    [(0, 20), (1, 0), (1, 101)],
)
def test_list_datasets_validates_pagination(page_number: int, page_size: int) -> None:
    with pytest.raises(ValueError):
        list_datasets(
            RecordingClient(),
            workspace_id="ws-1",
            page_number=page_number,
            page_size=page_size,
        )


def test_get_dataset_builds_request() -> None:
    client = RecordingClient()

    get_dataset(client, workspace_id="ws-1", dataset_id="ds-1")

    assert client.calls[0] == {
        "action": "GetDataset",
        "version": "2023-08-01",
        "service": "app",
        "body": {"WorkspaceID": "ws-1", "Id": "ds-1"},
    }


@pytest.mark.parametrize("workspace_id,dataset_id", [("", "ds-1"), ("ws-1", "")])
def test_get_dataset_requires_ids(workspace_id: str, dataset_id: str) -> None:
    with pytest.raises(ValueError):
        get_dataset(RecordingClient(), workspace_id=workspace_id, dataset_id=dataset_id)

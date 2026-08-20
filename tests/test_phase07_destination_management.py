from core.workspace_destinations import (
    can_manage_destinations,
    find_workspace_destination,
)


def test_only_owner_and_manager_can_manage_destinations():
    assert can_manage_destinations("owner") == (True, "")
    assert can_manage_destinations("manager") == (True, "")
    assert can_manage_destinations("publisher")[0] is False
    assert can_manage_destinations("writer")[0] is False


def test_find_destination_is_scoped_to_supplied_workspace_list():
    destinations = [
        {"id": 10, "status": "active"},
        {"id": 11, "status": "inactive"},
    ]
    assert find_workspace_destination(destinations, 11)["id"] == 11
    assert find_workspace_destination(destinations, 99) is None


def test_removed_destination_cannot_be_managed():
    destinations = [{"id": 10, "status": "removed"}]
    assert find_workspace_destination(destinations, 10) is None

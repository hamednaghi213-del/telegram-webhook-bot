from core.workspace_members import authorize_member_action


def test_owner_can_assign_all_non_owner_roles():
    for role in ("manager", "publisher", "writer"):
        assert authorize_member_action("owner", requested_role=role) == (True, "")


def test_manager_can_only_assign_publisher_or_writer():
    assert authorize_member_action("manager", requested_role="publisher") == (True, "")
    allowed, _ = authorize_member_action("manager", requested_role="manager")
    assert allowed is False


def test_non_manager_cannot_manage_members():
    allowed, _ = authorize_member_action("publisher", requested_role="writer")
    assert allowed is False


def test_owner_membership_is_immutable():
    allowed, _ = authorize_member_action("owner", target_role="owner")
    assert allowed is False


def test_manager_cannot_manage_another_manager():
    allowed, _ = authorize_member_action("manager", target_role="manager")
    assert allowed is False

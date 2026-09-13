from kodame_intake.admin import has_menu_permission


def test_report_permission_uses_admin_console_value_not_project_role() -> None:
    session = {
        "is_admin": False,
        "project_role": "viewer",
        "menu_permissions": {"evaluation_report": True},
    }

    assert has_menu_permission(session, "evaluation_report") is True


def test_explicit_admin_console_denial_blocks_report_permission() -> None:
    session = {
        "is_admin": False,
        "project_role": "owner",
        "menu_permissions": {"evaluation_report": False},
    }

    assert has_menu_permission(session, "evaluation_report") is False


def test_admin_and_legacy_permission_defaults() -> None:
    assert has_menu_permission({"is_admin": True, "menu_permissions": {"evaluation_report": False}}, "evaluation_report") is False
    assert has_menu_permission({"is_admin": False, "menu_permissions": {}}, "evaluation_report") is True
    assert has_menu_permission(None, "evaluation_report") is False
    assert has_menu_permission({"is_admin": False}, "unknown") is False

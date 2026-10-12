from invictusos_store.domain.catalog import (
	CATEGORY_SECTIONS,
	Package,
	package_action_label,
	count_installed_packages,
	package_issue_detail,
	package_matches_search,
	package_operation_status,
	package_status_is_negative,
	package_summary,
	parse_broken_packages,
	parse_dependency_issues,
	parse_held_packages,
	parse_upgradable_packages,
)


def test_package_defaults_are_uninstalled_and_unloaded() -> None:
	package = Package(name="example")

	assert package.name == "example"
	assert package.installed is False
	assert package.section_loaded is False


def test_categories_have_section_mappings() -> None:
	assert CATEGORY_SECTIONS["Development"] == {"devel"}
	assert "Media" in CATEGORY_SECTIONS


def test_action_label_uses_installed_state() -> None:
	assert package_action_label(Package(name="firefox")) == "Install"
	assert package_action_label(Package(name="firefox", installed=True)) == "Remove"
	assert package_action_label(None) == "Install"


def test_package_search_and_summary_helpers() -> None:
	package = Package(
		name="firefox",
		summary="Browser",
		description="Firefox is a free and open source web browser.\nIt has tabbed browsing.",
	)
	assert package_matches_search(package, "browser")
	assert package_matches_search(package, "tabbed")
	assert package_summary(package.description, package.summary) == "Firefox is a free and open source web browser."


def test_package_operation_status_messages() -> None:
	assert package_operation_status("install", "firefox", True) == "Successfully installed firefox."
	assert package_operation_status("remove", "firefox", False) == "Could not remove firefox."
	assert package_status_is_negative("install", True) is False
	assert package_status_is_negative("install", False) is True
	assert package_status_is_negative("remove", True) is True
	assert package_status_is_negative("remove", False) is True


def test_package_health_output_parsers() -> None:
	assert count_installed_packages("firefox\tii \nold-config\trc \n") == 1
	assert parse_broken_packages(
		"The following packages are unpacked:\n  example-package\n"
	) == ("example-package",)
	assert parse_upgradable_packages(
		"Inst firefox [1.0] (2.0 stable)\nConf firefox (2.0 stable)\n"
	) == ("firefox",)
	assert parse_held_packages("firefox\n\nlinux-image\n") == (
		"firefox",
		"linux-image",
	)
	assert parse_dependency_issues(
		"The following packages have unmet dependencies:\n"
		" app : Depends: missing-lib (>= 2) but it is not installable\n"
		" core : Conflicts: old-core\n"
	) == (
		("app", "Depends: missing-lib (>= 2) but it is not installable"),
		("core", "Conflicts: old-core"),
	)


def test_package_issue_detail_is_descriptive() -> None:
	assert package_issue_detail("broken", "example-package") == "Incomplete installation: example-package"
	assert package_issue_detail("upgradable", "firefox") == "Upgrade available: firefox"
	assert package_issue_detail("held", "linux-image") == "Package is on hold: linux-image"
	assert package_issue_detail(
		"dependency",
		"app",
		"Depends: missing-lib (>= 2) but it is not installable",
	) == "Depends: missing-lib (>= 2) but it is not installable"

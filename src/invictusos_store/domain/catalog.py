import re
from dataclasses import dataclass


@dataclass
class Package:
	name: str
	summary: str = ""
	version: str = ""
	description: str = ""
	installed: bool = False
	section: str = ""
	section_loaded: bool = False


def package_action_label(package: Package | None) -> str:
	return "Remove" if package and package.installed else "Install"


def package_summary(description: str | None, fallback: str = "") -> str:
	text = (description or fallback or "").strip()
	if not text:
		return ""
	text = re.sub(r"\s+", " ", text)
	for candidate in re.split(r"(?<=[.!?])\s+", text, maxsplit=1):
		candidate = candidate.strip()
		if candidate:
			return candidate
	return text


def package_matches_search(package: Package, query: str) -> bool:
	needle = query.strip().lower()
	if not needle:
		return True
	search_fields = [
		package.name,
		package.summary,
		package.description,
		package.section,
	]
	return any(needle in field.lower() for field in search_fields if field)


def package_operation_status(operation: str, name: str, success: bool) -> str:
	past_tense = "installed" if operation == "install" else "removed"
	if success:
		return f"Successfully {past_tense} {name}."
	return f"Could not {operation} {name}."


def package_status_is_negative(operation: str, success: bool) -> bool:
	return operation == "remove" or not success


def count_installed_packages(output: str) -> int:
	return sum(
		1
		for line in output.splitlines()
		if "\t" in line and line.rsplit("\t", 1)[1].startswith("ii")
	)


def parse_broken_packages(output: str) -> tuple[str, ...]:
	return tuple(
		line.strip()
		for line in output.splitlines()
		if line[:1].isspace() and line.strip()
	)


def parse_upgradable_packages(output: str) -> tuple[str, ...]:
	return tuple(
		fields[1]
		for line in output.splitlines()
		if line.startswith("Inst ")
	for fields in [line.split()]
		if len(fields) > 1
	)


def parse_held_packages(output: str) -> tuple[str, ...]:
	return tuple(line.strip() for line in output.splitlines() if line.strip())


def package_issue_detail(issue_type: str, package: str, detail: str = "") -> str:
	text = detail.strip()
	if issue_type == "dependency":
		return text or package
	if issue_type == "broken":
		return f"Incomplete installation: {package}"
	if issue_type == "upgradable":
		return f"Upgrade available: {package}"
	if issue_type == "held":
		return f"Package is on hold: {package}"
	if text:
		return text
	return package


def parse_dependency_issues(output: str) -> tuple[tuple[str, str], ...]:
	issues = []
	for line in output.splitlines():
		match = re.match(
			r"^\s*([a-zA-Z0-9][a-zA-Z0-9+.-]*(?::[a-zA-Z0-9-]+)?)\s*:\s*"
			r"(Depends|PreDepends|Conflicts|Breaks):\s*(.+)$",
			line,
			re.IGNORECASE,
		)
		if match:
			package, relation, detail = match.groups()
			issues.append((package, f"{relation}: {detail}"))
	return tuple(issues)


POPULAR_FALLBACK_PACKAGES = (
	"firefox-esr",
	"chromium",
	"thunderbird",
	"libreoffice-writer",
	"vlc",
	"gimp",
	"inkscape",
	"audacity",
	"blender",
	"obs-studio",
	"krita",
	"kdenlive",
	"filezilla",
	"keepassxc",
	"synaptic",
	"rhythmbox",
	"evince",
	"transmission-gtk",
)
POPULARITY_URL = "https://popcon.debian.org/by_inst.gz"
POPULAR_APP_SECTIONS = {
	"admin",
	"comm",
	"editors",
	"education",
	"games",
	"gnome",
	"graphics",
	"kde",
	"mail",
	"math",
	"misc",
	"net",
	"office",
	"science",
	"sound",
	"text",
	"utils",
	"video",
	"web",
	"x11",
}
CATEGORY_SECTIONS = {
	"Administration": {"admin"},
	"Communication": {"comm", "mail"},
	"Development": {"devel"},
	"Education": {"education"},
	"Games": {"games"},
	"Graphics": {"graphics"},
	"Internet": {"net", "web"},
	"Media": {"sound", "video"},
	"Office & Text": {"editors", "office", "text"},
	"Science & Math": {"math", "science"},
	"System & Utilities": {"gnome", "kde", "misc", "utils", "x11"},
}

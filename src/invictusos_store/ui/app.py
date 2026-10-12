#!/usr/bin/env python3
"""Desktop package browser for InvictusOS Sagaris and other APT-based systems."""

from __future__ import annotations

import gzip
import io
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable
from urllib.request import Request, urlopen

from ..domain.catalog import (
	CATEGORY_SECTIONS,
	POPULAR_APP_SECTIONS,
	POPULAR_FALLBACK_PACKAGES,
	POPULARITY_URL,
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
from .widgets import RoundedButton


try:
	APP_VERSION = version("invictusos-store")
except PackageNotFoundError:
	APP_VERSION = "0.1.0"


class AptStore:
	MAX_VISIBLE_PACKAGES = 500
	COLOR_BACKGROUND = "#15243a"
	COLOR_MAIN_TEXT = "#c7ddff"
	COLOR_ACCENT_TEXT = "#8fbbff"
	COLOR_SUBTITLE = "#3384ff"
	COLOR_ERROR = "#ff8b53"
	COLOR_WARNING = "#ffd166"
	COLOR_PANEL = "#1b2d47"

	def __init__(self, root: tk.Tk) -> None:
		self.root = root
		self.root.title("InvictusOS Store")
		self.root.configure(background=self.COLOR_BACKGROUND)
		self.root.geometry("600x400")
		self.root.minsize(600, 400)

		self.packages: dict[str, Package] = {}
		self.popular_packages: dict[str, Package] = {}
		self.installed_packages: list[Package] = []
		self.installed_loaded = False
		self.installed_loading = False
		self.popular_loaded = False
		self.popular_loading = False
		self.category_loading = False
		self.busy = False
		self.current_operation = ""
		self.active_jobs: dict[int, tuple[int, bool]] = {}
		self.next_job_id = 0
		self.results: queue.Queue[tuple[int, Callable, object, Exception | None]] = queue.Queue()
		self.progress_updates: queue.Queue[tuple[int, int]] = queue.Queue()
		self.search_after_id: str | None = None

		self._build_ui()
		self.root.after(100, self._drain_results)
		self.root.after(150, self._load_installed)

	def _build_ui(self) -> None:
		style = ttk.Style(self.root)
		style.theme_use("clam")
		style.configure(
			".",
			background=self.COLOR_BACKGROUND,
			foreground=self.COLOR_MAIN_TEXT,
			font=("Arimo", 10),
		)
		style.configure("TFrame", background=self.COLOR_BACKGROUND)
		style.configure("Accent.TFrame", background=self.COLOR_SUBTITLE)
		style.configure("Panel.TFrame", background=self.COLOR_PANEL)
		style.configure(
			"TLabel", background=self.COLOR_BACKGROUND, foreground=self.COLOR_MAIN_TEXT
		)
		style.configure(
			"Title.TLabel",
			background=self.COLOR_BACKGROUND,
			foreground=self.COLOR_MAIN_TEXT,
			font=("Arimo", 18, "bold"),
		)
		style.configure(
			"Subtitle.TLabel",
			background=self.COLOR_BACKGROUND,
			foreground=self.COLOR_SUBTITLE,
			font=("Arimo", 8, "bold"),
		)
		style.configure(
			"PackageHeading.TLabel",
			background=self.COLOR_PANEL,
			foreground=self.COLOR_MAIN_TEXT,
			font=("Arimo", 14, "bold"),
		)
		style.configure(
			"MetricName.TLabel",
			background=self.COLOR_PANEL,
			foreground=self.COLOR_ACCENT_TEXT,
			font=("Arimo", 9, "bold"),
		)
		style.configure(
			"MetricValue.TLabel",
			background=self.COLOR_PANEL,
			foreground=self.COLOR_MAIN_TEXT,
			font=("Arimo", 18, "bold"),
		)
		style.configure(
			"Status.TLabel",
			background=self.COLOR_BACKGROUND,
			foreground=self.COLOR_ACCENT_TEXT,
			padding=(8, 5),
			font=("Arimo", 9),
		)
		style.configure(
			"MenuItem.TLabel",
			background=self.COLOR_BACKGROUND,
			foreground=self.COLOR_ACCENT_TEXT,
			padding=(8, 4),
			font=("Arimo", 9, "bold"),
		)
		style.map(
			"MenuItem.TLabel",
			foreground=[("active", self.COLOR_MAIN_TEXT)],
		)
		style.configure(
			"Error.TLabel",
			background=self.COLOR_BACKGROUND,
			foreground=self.COLOR_WARNING,
			padding=(8, 5),
			font=("Arimo", 9, "bold"),
		)
		style.configure(
			"TEntry",
			fieldbackground=self.COLOR_PANEL,
			foreground=self.COLOR_MAIN_TEXT,
			selectbackground=self.COLOR_SUBTITLE,
			selectforeground=self.COLOR_MAIN_TEXT,
			padding=(8, 6),
			borderwidth=0,
			relief="flat",
		)
		style.configure(
			"TCombobox",
			fieldbackground=self.COLOR_PANEL,
			background=self.COLOR_PANEL,
			foreground=self.COLOR_MAIN_TEXT,
			arrowcolor=self.COLOR_ACCENT_TEXT,
			borderwidth=0,
			relief="flat",
			padding=(8, 5),
			highlightthickness=0,
			lightcolor=self.COLOR_PANEL,
			darkcolor=self.COLOR_PANEL,
		)
		style.map(
			"TCombobox",
			fieldbackground=[("readonly", self.COLOR_PANEL)],
			background=[("readonly", self.COLOR_PANEL)],
			foreground=[("readonly", self.COLOR_MAIN_TEXT)],
			selectbackground=[("readonly", self.COLOR_SUBTITLE)],
			selectforeground=[("readonly", self.COLOR_BACKGROUND)],
			bordercolor=[("readonly", self.COLOR_PANEL)],
			lightcolor=[("readonly", self.COLOR_PANEL)],
			darkcolor=[("readonly", self.COLOR_PANEL)],
		)
		style.configure(
			"Flat.TCombobox",
			fieldbackground=self.COLOR_PANEL,
			background=self.COLOR_PANEL,
			foreground=self.COLOR_MAIN_TEXT,
			arrowcolor=self.COLOR_ACCENT_TEXT,
			borderwidth=0,
			relief="flat",
			padding=(8, 5),
			highlightthickness=0,
			lightcolor=self.COLOR_PANEL,
			darkcolor=self.COLOR_PANEL,
		)
		style.map(
			"Flat.TCombobox",
			fieldbackground=[("readonly", self.COLOR_PANEL)],
			background=[("readonly", self.COLOR_PANEL)],
			foreground=[("readonly", self.COLOR_MAIN_TEXT)],
			selectbackground=[("readonly", self.COLOR_SUBTITLE)],
			selectforeground=[("readonly", self.COLOR_BACKGROUND)],
			bordercolor=[("readonly", self.COLOR_PANEL)],
			lightcolor=[("readonly", self.COLOR_PANEL)],
			darkcolor=[("readonly", self.COLOR_PANEL)],
		)
		style.configure(
			"ComboboxPopdownFrame",
			background=self.COLOR_PANEL,
			borderwidth=0,
			relief="flat",
			highlightthickness=0,
		)
		style.configure(
			"TCombobox.Listbox",
			background=self.COLOR_PANEL,
			foreground=self.COLOR_MAIN_TEXT,
			selectbackground=self.COLOR_SUBTITLE,
			selectforeground=self.COLOR_BACKGROUND,
			borderwidth=0,
			relief="flat",
			highlightthickness=0,
			lightcolor=self.COLOR_PANEL,
			darkcolor=self.COLOR_PANEL,
		)
		style.configure(
			"Minimal.Vertical.TScrollbar",
			background=self.COLOR_PANEL,
			troughcolor=self.COLOR_BACKGROUND,
			arrowcolor=self.COLOR_ACCENT_TEXT,
			borderwidth=0,
			relief="flat",
			lightcolor=self.COLOR_PANEL,
			darkcolor=self.COLOR_PANEL,
			gripcount=0,
		)
		style.map(
			"Minimal.Vertical.TScrollbar",
			background=[("active", self.COLOR_ACCENT_TEXT), ("pressed", self.COLOR_SUBTITLE)],
			arrowcolor=[("active", self.COLOR_BACKGROUND)],
		)
		style.configure(
			"Treeview",
			background=self.COLOR_PANEL,
			fieldbackground=self.COLOR_PANEL,
			foreground=self.COLOR_MAIN_TEXT,
			rowheight=26,
			font=("Arimo", 10),
			borderwidth=0,
			bordercolor=self.COLOR_PANEL,
			relief="flat",
		)
		style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
		style.map(
			"Treeview",
			background=[("selected", self.COLOR_SUBTITLE)],
			foreground=[("selected", self.COLOR_BACKGROUND)],
		)
		style.configure(
			"Treeview.Heading",
			background=self.COLOR_PANEL,
			foreground=self.COLOR_ACCENT_TEXT,
			font=("Arimo", 9, "bold"),
			padding=(8, 9),
			borderwidth=0,
			bordercolor=self.COLOR_PANEL,
			relief="flat",
			lightcolor=self.COLOR_PANEL,
			darkcolor=self.COLOR_PANEL,
		)
		style.configure(
			"TProgressbar",
			background=self.COLOR_SUBTITLE,
			troughcolor=self.COLOR_PANEL,
			bordercolor=self.COLOR_BACKGROUND,
			lightcolor=self.COLOR_PANEL,
			darkcolor=self.COLOR_PANEL,
			thickness=12,
		)
		style.configure(
			"TNotebook",
			background=self.COLOR_BACKGROUND,
			bordercolor=self.COLOR_BACKGROUND,
			borderwidth=0,
			relief="flat",
			lightcolor=self.COLOR_BACKGROUND,
			darkcolor=self.COLOR_BACKGROUND,
		)
		style.configure(
			"TNotebook.Tab",
			background=self.COLOR_PANEL,
			foreground=self.COLOR_ACCENT_TEXT,
			padding=(10, 6),
			font=("Arimo", 10, "bold"),
			borderwidth=0,
			bordercolor=self.COLOR_BACKGROUND,
			relief="flat",
			lightcolor=self.COLOR_PANEL,
			darkcolor=self.COLOR_PANEL,
			focuscolor=self.COLOR_PANEL,
		)
		style.map(
			"TNotebook.Tab",
			background=[("selected", self.COLOR_SUBTITLE)],
			foreground=[("selected", self.COLOR_BACKGROUND)],
			bordercolor=[("selected", self.COLOR_SUBTITLE)],
			lightcolor=[("selected", self.COLOR_SUBTITLE)],
			darkcolor=[("selected", self.COLOR_SUBTITLE)],
		)
		style.configure(
			"TPanedwindow",
			background=self.COLOR_BACKGROUND,
			borderwidth=0,
			relief="flat",
			sashthickness=2,
			sashpad=0,
			sashrelief="flat",
			handlesize=0,
			gripcount=0,
		)
		style.configure(
			"Sash",
			background=self.COLOR_BACKGROUND,
			borderwidth=0,
			relief="flat",
			lightcolor=self.COLOR_BACKGROUND,
			darkcolor=self.COLOR_BACKGROUND,
			gripcount=0,
		)

		shell = ttk.Frame(self.root, padding=(10, 8))
		shell.pack(fill="both", expand=True)

		header = ttk.Frame(shell)
		header.pack(fill="x", pady=(0, 8))
		identity = ttk.Frame(header)
		identity.pack(side="left", fill="y")
		ttk.Frame(identity, width=4, style="Accent.TFrame").pack(
			side="left", fill="y", padx=(0, 12)
		)
		brand_text = ttk.Frame(identity)
		brand_text.pack(side="left", anchor="w")
		ttk.Label(brand_text, text="InvictusOS Store", style="Title.TLabel").pack(
			anchor="w"
		)
		ttk.Label(brand_text, text="SYSTEM SOFTWARE", style="Subtitle.TLabel").pack(
			anchor="w", pady=(1, 0)
		)
		self.refresh_button = RoundedButton(
			header,
			text="Refresh package lists",
			command=self._refresh_lists,
			width=190,
			canvas_background=self.COLOR_BACKGROUND,
			background=self.COLOR_BACKGROUND,
			foreground=self.COLOR_ACCENT_TEXT,
			hover_background=self.COLOR_PANEL,
			disabled_background=self.COLOR_BACKGROUND,
			disabled_foreground=self.COLOR_PANEL,
		)
		self.refresh_button.pack(side="right", anchor="center")

		search_row = ttk.Frame(shell)
		search_row.pack(fill="x", pady=(0, 8))
		self.search_var = tk.StringVar()
		self.search_entry = tk.Entry(
			search_row,
			textvariable=self.search_var,
			background=self.COLOR_PANEL,
			foreground=self.COLOR_MAIN_TEXT,
			insertbackground=self.COLOR_ACCENT_TEXT,
			selectbackground=self.COLOR_SUBTITLE,
			selectforeground=self.COLOR_BACKGROUND,
			font=("Arimo", 10),
			borderwidth=0,
			highlightthickness=0,
			relief="flat",
		)
		self.search_entry.pack(side="left", fill="x", expand=True)
		self.search_entry.bind("<Return>", lambda _event: self._search())
		self.category_var = tk.StringVar(value="All categories")
		self.category_filter = ttk.Combobox(
			search_row,
			textvariable=self.category_var,
			values=("All categories", *CATEGORY_SECTIONS, "Other"),
			state="readonly",
			width=17,
			style="Flat.TCombobox",
		)
		self.category_filter.pack(side="left", padx=(8, 0))
		self.category_filter.bind(
			"<<ComboboxSelected>>", self._category_changed
		)
		self.search_button = RoundedButton(
			search_row,
			text="Search",
			command=self._search,
			width=88,
			canvas_background=self.COLOR_BACKGROUND,
			background=self.COLOR_SUBTITLE,
			foreground=self.COLOR_BACKGROUND,
			hover_background=self.COLOR_ACCENT_TEXT,
			disabled_background=self.COLOR_PANEL,
			disabled_foreground=self.COLOR_ACCENT_TEXT,
		)
		self.search_button.pack(side="left", padx=(8, 0))

		self.tabs = ttk.Notebook(shell)
		self.tabs.pack(fill="both", expand=True)
		self.popular_tab = ttk.Frame(self.tabs, padding=4)
		self.explore_tab = ttk.Frame(self.tabs, padding=4)
		self.installed_tab = ttk.Frame(self.tabs, padding=4)
		self.tools_tab = ttk.Frame(self.tabs, padding=12)
		self.tabs.add(self.popular_tab, text="Popular")
		self.tabs.add(self.explore_tab, text="Explore")
		self.tabs.add(self.installed_tab, text="Installed")
		self.tabs.add(self.tools_tab, text="System")
		self.tabs.bind("<<NotebookTabChanged>>", self._tab_changed)
		self._build_menubar()

		self._build_package_view(self.popular_tab, "popular")
		self._build_package_view(self.explore_tab, "explore")
		self._build_package_view(self.installed_tab, "installed")
		self._build_tools_view()

		footer = ttk.Frame(shell)
		footer.pack(fill="x", pady=(2, 0))
		self.status_var = tk.StringVar(value="Search Debian package repositories to get started.")
		self.status_label = ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel")
		self.operation_var = tk.StringVar(value="")
		self.operation_label = ttk.Label(footer, textvariable=self.operation_var, style="Status.TLabel")
		self.progress_bar = ttk.Progressbar(
			footer, mode="determinate", maximum=100, length=220
		)
		self.progress_bar.configure(
			style="TProgressbar",
			length=220,
			maximum=100,
		)
		self.action_button = RoundedButton(
			footer,
			text="Install",
			command=self._change_package_state,
			width=104,
			canvas_background=self.COLOR_BACKGROUND,
			background=self.COLOR_SUBTITLE,
			foreground=self.COLOR_BACKGROUND,
			hover_background=self.COLOR_ACCENT_TEXT,
			disabled_background=self.COLOR_PANEL,
			disabled_foreground=self.COLOR_ACCENT_TEXT,
			state="disabled",
		)
		self.progress_label = ttk.Label(footer, text="")
		footer.grid_columnconfigure(0, weight=1)
		footer.grid_columnconfigure(1, weight=0)
		footer.grid_columnconfigure(2, weight=0)
		footer.grid_columnconfigure(3, weight=0)
		footer.grid_columnconfigure(4, weight=0)
		self.status_label.grid(row=0, column=0, sticky="ew")
		self.operation_label.grid(row=0, column=1, sticky="e", padx=(0, 8))
		self.progress_bar.grid(row=0, column=2, sticky="ew", padx=(0, 0))
		self.progress_label.grid(row=0, column=3, sticky="e", padx=(6, 8))
		self.action_button.grid(row=0, column=4, sticky="e")

	def _build_menubar(self) -> None:
		menubar = tk.Menu(self.root, tearoff=0, bg=self.COLOR_PANEL, fg=self.COLOR_MAIN_TEXT,
			activebackground=self.COLOR_SUBTITLE, activeforeground=self.COLOR_BACKGROUND,
			bd=0, relief="flat")
		self.root.config(menu=menubar)

		file_menu = tk.Menu(menubar, tearoff=0, bg=self.COLOR_PANEL, fg=self.COLOR_MAIN_TEXT,
			activebackground=self.COLOR_SUBTITLE, activeforeground=self.COLOR_BACKGROUND,
			bd=0, relief="flat")
		file_menu.add_command(
			label="Refresh package lists",
			command=self._refresh_lists,
			accelerator="Ctrl+R",
		)
		file_menu.add_command(
			label="Package health check",
			command=self._show_package_health,
		)
		file_menu.add_separator()
		file_menu.add_command(label="Quit", command=self.root.destroy, accelerator="Ctrl+Q")
		menubar.add_cascade(label="File", menu=file_menu)

		edit_menu = tk.Menu(menubar, tearoff=0, bg=self.COLOR_PANEL, fg=self.COLOR_MAIN_TEXT,
			activebackground=self.COLOR_SUBTITLE, activeforeground=self.COLOR_BACKGROUND,
			bd=0, relief="flat")
		edit_menu.add_command(
			label="Search packages",
			command=self._focus_search,
			accelerator="Ctrl+L",
		)
		edit_menu.add_command(label="Reset filters", command=self._reset_filters)
		menubar.add_cascade(label="Edit", menu=edit_menu)

		view_menu = tk.Menu(menubar, tearoff=0, bg=self.COLOR_PANEL, fg=self.COLOR_MAIN_TEXT,
			activebackground=self.COLOR_SUBTITLE, activeforeground=self.COLOR_BACKGROUND,
			bd=0, relief="flat")
		for label, tab in (
			("Popular", self.popular_tab),
			("Explore", self.explore_tab),
			("Installed", self.installed_tab),
			("System", self.tools_tab),
		):
			view_menu.add_command(label=label, command=lambda page=tab: self.tabs.select(page))
		menubar.add_cascade(label="View", menu=view_menu)

		package_menu = tk.Menu(menubar, tearoff=0, bg=self.COLOR_PANEL, fg=self.COLOR_MAIN_TEXT,
			activebackground=self.COLOR_SUBTITLE, activeforeground=self.COLOR_BACKGROUND,
			bd=0, relief="flat")
		package_menu.add_command(label="Install / remove selected", command=self._change_package_state)
		package_menu.add_command(label="Repair dependencies", command=self._repair_dependencies)
		package_menu.add_separator()
		package_menu.add_command(
			label="Show installed packages",
			command=lambda: self.tabs.select(self.installed_tab),
		)
		menubar.add_cascade(label="Package", menu=package_menu)

		settings_menu = tk.Menu(menubar, tearoff=0, bg=self.COLOR_PANEL, fg=self.COLOR_MAIN_TEXT,
			activebackground=self.COLOR_SUBTITLE, activeforeground=self.COLOR_BACKGROUND,
			bd=0, relief="flat")
		settings_menu.add_command(label="Show package health", command=self._show_package_health)
		settings_menu.add_command(label="Refresh package lists", command=self._refresh_lists)
		menubar.add_cascade(label="Settings", menu=settings_menu)

		help_menu = tk.Menu(menubar, tearoff=0, bg=self.COLOR_PANEL, fg=self.COLOR_MAIN_TEXT,
			activebackground=self.COLOR_SUBTITLE, activeforeground=self.COLOR_BACKGROUND,
			bd=0, relief="flat")
		help_menu.add_command(label="About", command=self._show_about_dialog)
		menubar.add_cascade(label="Help", menu=help_menu)

		self.root.bind_all("<Control-r>", lambda _event: self._refresh_lists())
		self.root.bind_all("<Control-q>", lambda _event: self.root.destroy())
		self.root.bind_all("<Control-l>", lambda _event: self._focus_search())

	def _focus_search(self) -> None:
		self.tabs.select(self.explore_tab)
		self.search_entry.focus_set()
		self.search_entry.selection_range(0, tk.END)

	def _reset_filters(self) -> None:
		self.search_var.set("")
		self.category_var.set("All categories")
		selected_tab = self.tabs.select()
		if selected_tab == str(self.installed_tab):
			self._filter_installed()
		elif selected_tab == str(self.popular_tab):
			self._apply_category_filter("popular")
		else:
			self.tabs.select(self.explore_tab)
			self._apply_category_filter("explore")
		self.search_entry.focus_set()

	def _show_package_health(self) -> None:
		self.tabs.select(self.tools_tab)
		self._run_system_check()

	def _show_about_dialog(self) -> None:
		dialog = tk.Toplevel(self.root)
		dialog.title("About InvictusOS Store")
		dialog.configure(background=self.COLOR_BACKGROUND)
		dialog.transient(self.root)
		dialog.grab_set()

		content = ttk.Frame(dialog, padding=(24, 20), style="Panel.TFrame")
		content.pack(fill="both", expand=True)
		desc = tk.Label(
			content,
			text="InvictusOS Store",
			justify="left",
			fg=self.COLOR_MAIN_TEXT,
			bg=self.COLOR_PANEL,
			font=("Arimo", 17, "bold"),
		)
		desc.pack(anchor="w")

		tagline = tk.Label(
			content,
			text="A lightweight software centre for InvictusOS, designed to make discover, download and manage applications effortlessly.",
			wraplength=420,
			justify="left",
			fg=self.COLOR_ACCENT_TEXT,
			bg=self.COLOR_PANEL,
			font=("Arimo", 10),
		)
		tagline.pack(anchor="w", pady=(6, 16))

		metadata = (
			f"Version: {APP_VERSION}\n"
			f"Operating system: {platform.system()} {platform.release()}\n"
			f"Python: {platform.python_version()}\n"
			f"Interface: Tk {tk.TkVersion}\n"
			f"Package backend: {'APT' if shutil.which('apt-get') else 'Unavailable'}\n"
			"Designed for InvictusOS Sagaris and Debian-based distributions."
		)
		tk.Label(
			content,
			text=metadata,
			justify="left",
			anchor="w",
			fg=self.COLOR_MAIN_TEXT,
			bg=self.COLOR_PANEL,
			font=("Arimo", 9),
		).pack(anchor="w", fill="x", pady=(0, 12))

		website = ttk.Button(
			content,
			text="https://webinvictusos.neocities.org/",
			command=lambda: self._open_about_website(dialog),
		)
		website.pack(anchor="w", pady=(0, 14))

		button = ttk.Button(content, text="Close", command=dialog.destroy)
		button.pack(anchor="e")

		dialog.update_idletasks()
		dialog.geometry("480x370")
		dialog.minsize(440, 340)

	def _open_about_website(self, dialog: tk.Toplevel) -> None:
		try:
			opened = webbrowser.open_new_tab("https://webinvictusos.neocities.org/")
		except webbrowser.Error as error:
			messagebox.showerror("Could not open website", str(error), parent=dialog)
			return
		if not opened:
			messagebox.showerror(
				"Could not open website",
				"No browser could open https://webinvictusos.neocities.org/.",
				parent=dialog,
			)

	def _build_tools_view(self) -> None:
		header = ttk.Frame(self.tools_tab)
		header.pack(fill="x", pady=(0, 10))
		title = ttk.Label(header, text="Package health", style="PackageHeading.TLabel")
		title.pack(side="left", anchor="center")
		self.tools_repair_button = RoundedButton(
			header,
			text="Repair dependencies",
			command=self._repair_dependencies,
			width=168,
			canvas_background=self.COLOR_BACKGROUND,
			background=self.COLOR_SUBTITLE,
			foreground=self.COLOR_BACKGROUND,
			hover_background=self.COLOR_ACCENT_TEXT,
			disabled_background=self.COLOR_PANEL,
			disabled_foreground=self.COLOR_ACCENT_TEXT,
		)
		self.tools_repair_button.pack(side="right", padx=(8, 0))
		self.tools_check_button = RoundedButton(
			header,
			text="Run checks",
			command=self._run_system_check,
			width=112,
			canvas_background=self.COLOR_BACKGROUND,
			background=self.COLOR_SUBTITLE,
			foreground=self.COLOR_BACKGROUND,
			hover_background=self.COLOR_ACCENT_TEXT,
			disabled_background=self.COLOR_PANEL,
			disabled_foreground=self.COLOR_ACCENT_TEXT,
		)
		self.tools_check_button.pack(side="right")

		metrics = ttk.Frame(self.tools_tab)
		metrics.pack(fill="x", pady=(0, 10))
		self.tool_metric_vars: dict[str, tk.StringVar] = {}
		metric_items = (
			("installed", "Installed packages"),
			("broken", "Broken packages"),
			("upgradable", "Upgradable"),
			("held", "On hold"),
		)
		for index, (key, label) in enumerate(metric_items):
			cell = ttk.Frame(metrics, style="Panel.TFrame", padding=(10, 8))
			cell.grid(row=index // 2, column=index % 2, sticky="nsew", padx=(0, 8), pady=(0, 8))
			metrics.grid_columnconfigure(index % 2, weight=1)
			ttk.Label(cell, text=label, style="MetricName.TLabel").pack(anchor="w")
			value = tk.StringVar(value="--")
			self.tool_metric_vars[key] = value
			ttk.Label(cell, textvariable=value, style="MetricValue.TLabel").pack(anchor="w")

		ttk.Label(
			self.tools_tab,
			text="Package issues",
			style="PackageHeading.TLabel",
		).pack(anchor="w", pady=(0, 6))
		issues_frame = ttk.Frame(self.tools_tab)
		issues_frame.pack(fill="both", expand=True)
		self.tools_issues = ttk.Treeview(
			issues_frame,
			columns=("package", "issue"),
			show="headings",
			selectmode="browse",
			height=5,
		)
		self.tools_issues.heading("package", text="Package")
		self.tools_issues.heading("issue", text="Issue")
		self.tools_issues.column("package", width=130, minwidth=90, stretch=False)
		self.tools_issues.column("issue", width=340, minwidth=160)
		issues_scrollbar = ttk.Scrollbar(
			issues_frame,
			orient="vertical",
			command=self.tools_issues.yview,
			style="Minimal.Vertical.TScrollbar",
		)
		self.tools_issues.configure(yscrollcommand=issues_scrollbar.set)
		self.tools_issues.pack(side="left", fill="both", expand=True)
		issues_scrollbar.pack(side="right", fill="y")
		self.tools_check_running = False

	def _build_package_view(self, parent: ttk.Frame, view: str) -> None:
		pane = ttk.Panedwindow(parent, orient="horizontal")
		pane.pack(fill="both", expand=True)

		list_frame = ttk.Frame(pane, style="Panel.TFrame", padding=0)
		detail_frame = ttk.Frame(pane, style="Panel.TFrame", padding=(8, 6, 6, 6))
		pane.add(list_frame, weight=3)
		pane.add(detail_frame, weight=2)

		tree = ttk.Treeview(
			list_frame,
			columns=("name", "summary"),
			show="headings",
			selectmode="browse",
		)
		tree.heading("name", text="Package")
		tree.heading("summary", text="Description")
		tree.column("name", width=130, minwidth=90, stretch=False)
		tree.column("summary", width=220, minwidth=100)
		scrollbar = ttk.Scrollbar(
			list_frame,
			orient="vertical",
			command=tree.yview,
			style="Minimal.Vertical.TScrollbar",
		)
		tree.configure(yscrollcommand=scrollbar.set)
		tree.pack(side="left", fill="both", expand=True)
		scrollbar.pack(side="right", fill="y")

		title_row = ttk.Frame(detail_frame)
		title_row.pack(fill="x", pady=(0, 8))
		heading = ttk.Label(
			title_row, text="Select a package", style="PackageHeading.TLabel"
		)
		heading.pack(side="left", anchor="center", fill="x", expand=True)
		description_row = ttk.Frame(detail_frame)
		description_row.pack(fill="both", expand=True)
		details = tk.Canvas(
			description_row,
			background=self.COLOR_BACKGROUND,
			highlightthickness=0,
			yscrollincrement=18,
		)
		details_scrollbar = ttk.Scrollbar(
			description_row,
			orient="vertical",
			command=details.yview,
			style="Minimal.Vertical.TScrollbar",
		)
		details.configure(yscrollcommand=details_scrollbar.set)
		details.pack(side="left", fill="both", expand=True)
		details_scrollbar.pack(side="right", fill="y")
		details.create_rectangle(
			12, 12, 200, 60, fill=self.COLOR_PANEL, outline="", state="hidden", tags="version_box"
		)
		details.create_rectangle(
			12, 68, 200, 116, fill=self.COLOR_PANEL, outline="", state="hidden", tags="section_box"
		)
		details.create_text(
			22,
			20,
			anchor="nw",
			text="VERSION",
			fill=self.COLOR_SUBTITLE,
			font=("Arimo", 8, "bold"),
			state="hidden",
			tags="version_label",
		)
		details.create_text(
			22,
			36,
			anchor="nw",
			width=260,
			fill=self.COLOR_MAIN_TEXT,
			font=("Arimo", 10),
			state="hidden",
			tags="version_value",
		)
		details.create_text(
			22,
			76,
			anchor="nw",
			text="SECTION",
			fill=self.COLOR_SUBTITLE,
			font=("Arimo", 8, "bold"),
			state="hidden",
			tags="section_label",
		)
		details.create_text(
			22,
			92,
			anchor="nw",
			width=260,
			fill=self.COLOR_MAIN_TEXT,
			font=("Arimo", 10),
			state="hidden",
			tags="section_value",
		)
		details.create_text(
			12,
			12,
			anchor="nw",
			width=300,
			fill=self.COLOR_MAIN_TEXT,
			font=("Arimo", 10),
			tags="description",
		)
		details.bind("<Configure>", self._resize_description)

		tree.bind("<<TreeviewSelect>>", lambda _event, key=view: self._selection_changed(key))
		setattr(self, f"{view}_tree", tree)
		setattr(self, f"{view}_heading", heading)
		setattr(self, f"{view}_details", details)

	def _run_background(self, work: Callable, done: Callable, priority: bool = False) -> None:
		self.next_job_id += 1
		job_id = self.next_job_id
		was_idle = not self.active_jobs
		self.active_jobs[job_id] = (1, priority)
		if was_idle:
			self.progress_bar.grid(row=0, column=1, sticky="ew", padx=(10, 0))
			self.progress_label.grid(row=0, column=2, sticky="e", padx=(6, 8))
		self._update_progress_display()

		def report_progress(percent: int) -> None:
			self.progress_updates.put((job_id, max(1, min(100, percent))))

		def run() -> None:
			try:
				result = work(report_progress)
				report_progress(100)
				self.results.put((job_id, done, result, None))
			except Exception as error:
				self.results.put((job_id, done, None, error))

		threading.Thread(target=run, daemon=True).start()

	def _drain_results(self) -> None:
		while True:
			try:
				job_id, percent = self.progress_updates.get_nowait()
			except queue.Empty:
				break
			if job_id in self.active_jobs:
				_, priority = self.active_jobs[job_id]
				self.active_jobs[job_id] = (percent, priority)
				self._update_progress_display()
		while True:
			try:
				job_id, callback, result, error = self.results.get_nowait()
			except queue.Empty:
				break
			self.active_jobs.pop(job_id, None)
			self._update_progress_display()
			callback(result, error)
		self.root.after(100, self._drain_results)

	def _update_progress_display(self) -> None:
		if not self.active_jobs:
			self.operation_var.set("")
			self.progress_bar.grid_remove()
			self.progress_label.grid_remove()
			self.operation_label.grid_remove()
			return
		self.operation_var.set(self.current_operation or "Working")
		self.progress_bar.grid()
		self.progress_label.grid()
		self.operation_label.grid()
		priorities = [percent for percent, priority in self.active_jobs.values() if priority]
		values = priorities or [percent for percent, _priority in self.active_jobs.values()]
		average = round(sum(values) / len(values))
		self.progress_bar.configure(value=average)
		self.progress_label.configure(text=f"{average}%")

	def _set_busy(self, busy: bool, status: str | None = None) -> None:
		self.busy = busy
		self.current_operation = status.strip("…") if status else ""
		state = "disabled" if busy else "normal"
		self.search_button.configure(state=state)
		self.refresh_button.configure(state=state)
		self.category_filter.configure(
			state="disabled" if busy or self.category_loading else "readonly"
		)
		self.action_button.configure(state="disabled" if busy else self._action_state())
		if status:
			self._set_status(status)

	def _set_status(self, text: str, error: bool = False) -> None:
		self.status_var.set(text)
		self.status_label.configure(style="Error.TLabel" if error else "Status.TLabel")

	def _populate_tool_issues(self, issues: list[tuple[str, str]]) -> None:
		self.tools_issues.delete(*self.tools_issues.get_children())
		if not issues:
			self.tools_issues.insert("", "end", values=("", "No package issues found"))
			return
		for package, issue in issues:
			self.tools_issues.insert("", "end", values=(package, issue))

	def _fetch_apt_policy(self, packages: list[str]) -> dict[str, str]:
		if not packages:
			return {}
		if not shutil.which("apt-cache"):
			return {package: "apt-cache is not available." for package in packages}

		policies: dict[str, str] = {}
		for start in range(0, len(packages), 40):
			batch = packages[start:start + 40]
			try:
				output = self._command(["apt-cache", "policy", *batch], timeout=60)
			except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
				for package in batch:
					policies[package] = f"APT policy lookup failed: {error}"
				continue

			sections: dict[str, list[str]] = {}
			current_package = ""
			for line in output.splitlines():
				if line and not line[0].isspace() and line.endswith(":"):
					candidate = line[:-1]
					current_package = candidate if candidate in batch else ""
				if current_package:
					sections.setdefault(current_package, []).append(line)
			for package in batch:
				policy = "\n".join(sections.get(package, ()))
				policies[package] = policy or "No APT policy information returned."
		return policies

	def _show_package_issues(
		self,
		issues: list[tuple[str, str]],
		apt_policy: dict[str, str],
	) -> None:
		dialog = tk.Toplevel(self.root)
		dialog.title(f"Package issues found ({len(issues)})")
		dialog.configure(background=self.COLOR_BACKGROUND)
		dialog.transient(self.root)
		dialog.geometry("900x560")
		dialog.minsize(700, 420)

		content = ttk.Frame(dialog, padding=12)
		content.pack(fill="both", expand=True)
		pane = ttk.Panedwindow(content, orient="horizontal")
		pane.pack(fill="both", expand=True)

		issue_frame = ttk.Frame(pane)
		detail_frame = ttk.Frame(pane)
		pane.add(issue_frame, weight=2)
		pane.add(detail_frame, weight=3)

		issue_tree = ttk.Treeview(
			issue_frame,
			columns=("package", "issue"),
			show="headings",
			selectmode="browse",
		)
		issue_tree.heading("package", text="Package")
		issue_tree.heading("issue", text="Detected issue")
		issue_tree.column("package", width=150, minwidth=100, stretch=False)
		issue_tree.column("issue", width=240, minwidth=140)
		issue_scrollbar = ttk.Scrollbar(
			issue_frame,
			orient="vertical",
			command=issue_tree.yview,
			style="Minimal.Vertical.TScrollbar",
		)
		issue_tree.configure(yscrollcommand=issue_scrollbar.set)
		issue_tree.pack(side="left", fill="both", expand=True)
		issue_scrollbar.pack(side="right", fill="y")

		detail_scrollbar = ttk.Scrollbar(
			detail_frame,
			orient="vertical",
			style="Minimal.Vertical.TScrollbar",
		)
		detail_text = tk.Text(
			detail_frame,
			wrap="word",
			background=self.COLOR_PANEL,
			foreground=self.COLOR_MAIN_TEXT,
			insertbackground=self.COLOR_MAIN_TEXT,
			relief="flat",
			padx=12,
			pady=10,
			yscrollcommand=detail_scrollbar.set,
		)
		detail_scrollbar.configure(command=detail_text.yview)
		detail_text.pack(side="left", fill="both", expand=True)
		detail_scrollbar.pack(side="right", fill="y")

		def show_details(_event: object = None) -> None:
			selection = issue_tree.selection()
			if not selection:
				return
			package, issue = issue_tree.item(selection[0], "values")
			package_match = re.match(
				r"^([A-Za-z0-9][A-Za-z0-9+.-]*(?::[A-Za-z0-9-]+)?)(?=$|[\\s:])",
				package,
			)
			apt_name = package_match.group(1) if package_match else ""
			policy = apt_policy.get(apt_name, "No APT policy information available for this entry.")
			detail = f"Package: {package}\n\nDetected issue:\n{issue}\n\nAPT policy:\n{policy}"
			detail_text.configure(state="normal")
			detail_text.delete("1.0", "end")
			detail_text.insert("1.0", detail)
			detail_text.configure(state="disabled")

		for index, (package, issue) in enumerate(issues):
			issue_tree.insert("", "end", iid=str(index), values=(package, issue))
		issue_tree.bind("<<TreeviewSelect>>", show_details)
		issue_tree.selection_set("0")
		show_details()

	def _run_system_check(self) -> None:
		if self.tools_check_running or self.busy:
			return
		self.tools_check_running = True
		self.tools_check_button.configure(state="disabled")
		self.tools_repair_button.configure(state="disabled")
		self._set_status("Checking installed packages and APT health…")

		def work(progress: Callable[[int], None]) -> dict[str, object]:
			installed_output = self._command(
				[
					"dpkg-query",
					"-W",
					"-f=${binary:Package}\t${db:Status-Abbrev}\n",
				]
			)
			progress(20)
			broken_output = self._command(["dpkg", "--audit"])
			progress(40)
			upgrade_output = self._command(["apt-get", "-s", "upgrade"], timeout=120)
			progress(60)
			held_output = self._command(["apt-mark", "showhold"])
			progress(80)
			dependency_error = ""
			dependency_output = ""
			try:
				dependency_output = self._command(["apt-get", "check"], timeout=120)
			except RuntimeError as error:
				dependency_error = str(error)
				dependency_output = dependency_error
			broken = parse_broken_packages(broken_output)
			upgradable = parse_upgradable_packages(upgrade_output)
			held = parse_held_packages(held_output)
			dependency_issues = parse_dependency_issues(dependency_output)
			issues = [
				(package, package_issue_detail("broken", package)) for package in broken
			]
			issues.extend(
				(package, package_issue_detail("upgradable", package)) for package in upgradable
			)
			issues.extend(
				(package, package_issue_detail("held", package)) for package in held
			)
			issues.extend(
				(package, package_issue_detail("dependency", package, detail))
				for package, detail in dependency_issues
			)
			if dependency_error and not dependency_issues:
				issues.append(("APT", dependency_error))
			apt_names = set()
			for package, _issue in issues:
				match = re.match(
					r"^([A-Za-z0-9][A-Za-z0-9+.-]*(?::[A-Za-z0-9-]+)?)(?=$|[\\s:])",
					package,
				)
				if match:
					apt_names.add(match.group(1))
			apt_policy = self._fetch_apt_policy(sorted(apt_names))
			progress(100)
			return {
				"installed": count_installed_packages(installed_output),
				"broken": broken,
				"upgradable": upgradable,
				"held": held,
				"dependency_error": dependency_error,
				"dependency_issues": dependency_issues,
				"issues": issues,
				"apt_policy": apt_policy,
			}

		self._run_background(work, self._system_check_finished)

	def _system_check_finished(self, result: object, error: Exception | None) -> None:
		self.tools_check_running = False
		self.tools_check_button.configure(state="normal")
		self.tools_repair_button.configure(state="normal")
		if error:
			self._populate_tool_issues([("APT", str(error))])
			self._set_status(f"System check failed: {error}", error=True)
			return

		broken = result["broken"]
		upgradable = result["upgradable"]
		held = result["held"]
		dependency_error = result["dependency_error"]
		dependency_issues = result["dependency_issues"]
		self.tool_metric_vars["installed"].set(str(result["installed"]))
		self.tool_metric_vars["broken"].set(str(len(broken)))
		self.tool_metric_vars["upgradable"].set(str(len(upgradable)))
		self.tool_metric_vars["held"].set(str(len(held)))

		issues = result["issues"]
		self._populate_tool_issues(issues)
		if issues:
			self._show_package_issues(issues, result["apt_policy"])
		self._set_status(
			"System checks complete." if not broken and not dependency_error else "Package health issues found.",
			error=bool(broken or dependency_error),
		)

	def _repair_dependencies(self) -> None:
		if self.busy or self.tools_check_running:
			return
		if not shutil.which("pkexec") or not shutil.which("apt-get"):
			self._show_error("Dependency repair requires APT and graphical authorization (pkexec).")
			return
		if not messagebox.askyesno(
			"Repair package dependencies?",
			"APT may install or remove packages to repair dependency problems. Continue?",
			parent=self.root,
		):
			return

		self.tools_check_button.configure(state="disabled")
		self.tools_repair_button.configure(state="disabled")
		self._set_busy(True, "Waiting for authorization to repair package dependencies…")

		def work(progress: Callable[[int], None]) -> str:
			progress(5)
			return self._command(
				["pkexec", "apt-get", "-y", "-f", "install"],
				timeout=3600,
				progress=progress,
			)

		def done(_result: object, error: Exception | None) -> None:
			self._set_busy(False)
			self.tools_check_button.configure(state="normal")
			self.tools_repair_button.configure(state="normal")
			if error:
				self._show_error(f"Dependency repair failed:\n{error}")
				return
			self._set_status("Dependency repair finished. Running checks again…")
			self._run_system_check()

		self._run_background(work, done, priority=True)

	@staticmethod
	def _command(
		args: list[str],
		timeout: int = 30,
		progress: Callable[[int], None] | None = None,
	) -> str:
		if progress is None:
			completed = subprocess.run(
				args,
				check=False,
				capture_output=True,
				text=True,
				timeout=timeout,
			)
			stdout = completed.stdout
			returncode = completed.returncode
		else:
			process = subprocess.Popen(
				args,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				text=True,
				bufsize=1,
			)
			output: list[str] = []
			last_percent = 0

			def read_output() -> None:
				nonlocal last_percent
				if process.stdout is None:
					return
				for line in process.stdout:
					output.append(line)
					match = re.search(r"(\d{1,3})\s*%", line)
					if match:
						last_percent = max(last_percent, min(100, int(match.group(1))))
						progress(5 + round(last_percent * 0.9))

			reader = threading.Thread(target=read_output, daemon=True)
			reader.start()
			try:
				returncode = process.wait(timeout=timeout)
			except subprocess.TimeoutExpired:
				process.kill()
				process.wait()
				reader.join()
				raise
			reader.join()
			stdout = "".join(output)

		if returncode != 0:
			detail = stdout.strip()
			raise RuntimeError(detail or f"Command exited with status {returncode}.")
		return stdout

	def _search(self) -> None:
		query = self.search_var.get().strip()
		if not query:
			self._set_status("Enter a package name or keyword to search.")
			self.search_entry.focus_set()
			return
		if not shutil.which("apt-cache"):
			self._show_error("APT is not available. Run this app on a Debian-based system.")
			return

		self.tabs.select(self.explore_tab)
		self._set_busy(True, f"Searching for {query!r}…")

		def work(progress: Callable[[int], None]) -> tuple[list[Package], bool]:
			progress(5)
			output = self._command(["apt-cache", "search", "--", query])
			progress(15)
			packages = []
			truncated = False
			for line in io.StringIO(output):
				name, separator, summary = line.partition(" - ")
				if separator and name:
					if len(packages) >= self.MAX_VISIBLE_PACKAGES:
						truncated = True
						break
					packages.append(Package(name=name, summary=summary.strip()))
				progress(15 + round(84 * len(packages) / self.MAX_VISIBLE_PACKAGES))
			return packages, truncated

		self._run_background(work, self._search_finished)

	def _search_finished(self, result: object, error: Exception | None) -> None:
		self._set_busy(False)
		if error:
			self._show_error(f"Package search failed: {error}")
			return
		packages, truncated = result
		self.packages = {package.name: package for package in packages}
		shown = self._apply_category_filter("explore")
		if shown is None:
			return
		count = len(self.packages)
		if self.category_var.get() != "All categories":
			self._set_category_status(shown)
		elif truncated:
			self._set_status(
				f"Showing the first {count} results. Refine your search to narrow results."
			)
		else:
			self._set_status(f"{count} package{'s' if count != 1 else ''} found.")

	def _category_changed(self, _event: tk.Event) -> None:
		shown = self._apply_category_filter()
		if shown is not None:
			self._set_category_status(shown)

	def _apply_category_filter(self, view: str | None = None) -> int | None:
		if view is None:
			selected_tab = self.tabs.select()
			if selected_tab == str(self.installed_tab):
				view = "installed"
			elif selected_tab == str(self.popular_tab):
				view = "popular"
			elif selected_tab == str(self.tools_tab):
				return None
			else:
				view = "explore"

		query = self.search_var.get().strip()
		if view == "installed":
			packages = [
				package for package in self.installed_packages if package_matches_search(package, query)
			]
		elif view == "popular":
			packages = [
				package for package in self.popular_packages.values() if package_matches_search(package, query)
			]
		else:
			packages = [
				package for package in self.packages.values() if package_matches_search(package, query)
			]
		tree = getattr(self, f"{view}_tree")
		category = self.category_var.get()
		if category == "All categories":
			return self._populate_tree(tree, packages)

		missing = [package for package in packages if not package.section_loaded]
		if missing:
			self._load_category_sections(view, missing)
			return None

		known_sections = set().union(*CATEGORY_SECTIONS.values())
		if category == "Other":
			filtered = [
				package
				for package in packages
				if package.section.lower().split("/")[-1] not in known_sections
			]
		else:
			sections = CATEGORY_SECTIONS[category]
			filtered = [
				package
				for package in packages
				if package.section.lower().split("/")[-1] in sections
			]
		return self._populate_tree(tree, filtered)

	def _set_category_status(self, count: int) -> None:
		category = self.category_var.get()
		if category == "All categories":
			self._set_status(f"Showing {count} packages.")
		else:
			self._set_status(f"Showing {count} packages in {category}.")

	def _load_category_sections(self, view: str, packages: list[Package]) -> None:
		if self.category_loading:
			return
		self.category_loading = True
		self.category_filter.configure(state="disabled")
		self._set_status("Loading package categories…")
		package_names = list(
			dict.fromkeys(package.name.split(":", 1)[0] for package in packages)
		)

		def work(progress: Callable[[int], None]) -> dict[str, str]:
			batch_size = 100
			total_batches = max(1, (len(package_names) + batch_size - 1) // batch_size)
			sections: dict[str, str] = {}
			for batch_index, start in enumerate(
				range(0, len(package_names), batch_size), start=1
			):
				batch = package_names[start:start + batch_size]
				output = self._command(["apt-cache", "show", *batch], timeout=60)
				for stanza in output.split("\n\n"):
					name = ""
					section = ""
					for line in stanza.splitlines():
						if line[:1].isspace() or ": " not in line:
							continue
						key, value = line.split(": ", 1)
						if key == "Package":
							name = value
						elif key == "Section":
							section = value
					if name and section:
						sections.setdefault(name, section)
				progress(5 + round(94 * batch_index / total_batches))
			return sections

		def done(result: object, error: Exception | None) -> None:
			self.category_loading = False
			self.category_filter.configure(
				state="disabled" if self.busy else "readonly"
			)
			if error:
				for package in packages:
					package.section_loaded = True
				self._set_status(f"Could not load package categories: {error}", error=True)
				return
			for package in packages:
				package.section = result.get(package.name.split(":", 1)[0], "")
				package.section_loaded = True
			shown = self._apply_category_filter()
			if shown is not None:
				self._set_category_status(shown)

		self._run_background(work, done)

	def _load_installed(self) -> None:
		if self.installed_loaded or self.installed_loading or not shutil.which("dpkg-query"):
			return
		self.installed_loading = True
		self._set_status("Loading installed packages…")

		def work(progress: Callable[[int], None]) -> list[Package]:
			progress(5)
			output = self._command(
				[
					"dpkg-query",
					"-W",
					"-f=${binary:Package}\t${Version}\t${db:Status-Abbrev}\t${binary:Summary}\t${Section}\n",
				]
			)
			progress(15)
			packages = []
			lines = output.splitlines()
			for index, line in enumerate(lines):
				fields = line.split("\t", 4)
				if len(fields) == 5 and fields[2].startswith("ii"):
					packages.append(
						Package(
							fields[0],
							fields[3],
							fields[1],
							installed=True,
							section=fields[4],
							section_loaded=bool(fields[4]),
						)
					)
				progress(15 + round(84 * (index + 1) / max(1, len(lines))))
			return packages

		self._run_background(work, self._installed_finished)

	def _installed_finished(self, result: object, error: Exception | None) -> None:
		self.installed_loading = False
		if error:
			self._set_status(f"Could not read installed packages: {error}", error=True)
			return
		self.installed_loaded = True
		self.installed_packages = result
		shown = self._filter_installed()
		if shown is None:
			return
		if self.category_var.get() != "All categories":
			self._set_category_status(shown)
			return
		if shown < len(self.installed_packages):
			self._set_status(
				f"Showing {shown} of {len(self.installed_packages)} installed packages."
			)
		else:
			self._set_status(f"{len(self.installed_packages)} installed packages.")

	def _filter_installed(self) -> int | None:
		return self._apply_category_filter("installed")

	def _load_popular(self) -> None:
		if self.popular_loaded or self.popular_loading:
			return
		if not shutil.which("apt-cache"):
			self._set_status("APT is not available on this system.", error=True)
			return
		self.popular_loading = True
		self._set_status("Loading popular apps from APT…")

		def work(progress: Callable[[int], None]) -> tuple[list[Package], bool]:
			progress(5)
			used_fallback = False
			try:
				ranking = self._load_popularity_ranking()
			except (OSError, RuntimeError, EOFError, gzip.BadGzipFile, ValueError):
				ranking = list(enumerate(POPULAR_FALLBACK_PACKAGES, start=1))
				used_fallback = True
			progress(25)
			ranked_names = [name for _rank, name in ranking[:5000]]
			batch_size = 500
			total_batches = max(1, (len(ranked_names) + batch_size - 1) // batch_size)
			installed_names = {
				package.name.split(":", 1)[0] for package in self.installed_packages
			}
			if not self.installed_loaded and shutil.which("dpkg-query"):
				installed_output = self._command(
					[
						"dpkg-query",
						"-W",
						"-f=${binary:Package}\t${db:Status-Abbrev}\n",
					]
				)
				installed_names.update(
					line.split("\t", 1)[0].split(":", 1)[0]
					for line in installed_output.splitlines()
					if "\t" in line and line.split("\t", 1)[1].startswith("ii")
				)
			progress(35)
			available: dict[str, Package] = {}
			for batch_index, start in enumerate(range(0, len(ranked_names), batch_size), start=1):
				batch = ranked_names[start:start + batch_size]
				batch_names = set(batch)
				output = self._command(["apt-cache", "show", *batch], timeout=60)
				for stanza in output.split("\n\n"):
					fields: dict[str, str] = {}
					current_field = ""
					for line in stanza.splitlines():
						if line[:1].isspace() and current_field:
							fields[current_field] += "\n" + line.strip()
						elif ": " in line:
							current_field, value = line.split(": ", 1)
							fields[current_field] = value
					name = fields.get("Package", "")
					section = fields.get("Section", "").split("/")[-1].lower()
					if (
						name in batch_names
						and section in POPULAR_APP_SECTIONS
						and name not in available
					):
						description = fields.get("Description", "")
						available[name] = Package(
							name=name,
							summary=description.splitlines()[0] if description else name,
							version=fields.get("Version", ""),
							description=description,
							installed=name in installed_names,
							section=fields.get("Section", ""),
							section_loaded=True,
						)
				progress(35 + round(63 * batch_index / total_batches))
				if len(available) >= 60:
					break
			ordered_names = [name for name in ranked_names if name in available]
			return [available[name] for name in ordered_names[:60]], used_fallback

		self._run_background(work, self._popular_finished)

	def _popular_finished(self, result: object, error: Exception | None) -> None:
		self.popular_loading = False
		if error:
			self._set_status(f"Could not load popular apps: {error}", error=True)
			return
		self.popular_loaded = True
		packages, used_fallback = result
		self.popular_packages = {package.name: package for package in packages}
		shown = self._apply_category_filter("popular")
		if shown is None:
			return
		if self.category_var.get() != "All categories":
			self._set_category_status(shown)
			return
		if used_fallback:
			self._set_status(
				f"Showing {len(self.popular_packages)} recommendations; popularity data is offline."
			)
		else:
			self._set_status(
				f"{len(self.popular_packages)} popular apps ranked by Debian install counts."
			)

	@staticmethod
	def _parse_popularity_ranking(compressed: bytes) -> list[tuple[int, str]]:
		text = gzip.decompress(compressed).decode("utf-8", "replace")
		ranking = []
		for line in text.splitlines():
			fields = line.split()
			if len(fields) < 7 or not fields[0].isdigit() or not fields[2].isdigit():
				continue
			name = fields[1]
			if re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", name):
				rank = int(fields[0])
				if rank <= 5000:
					ranking.append((rank, name))
		return ranking

	@classmethod
	def _load_popularity_ranking(cls) -> list[tuple[int, str]]:
		cache = Path.home() / ".cache" / "apt-store" / "popcon-by-installed.gz"
		cached_data = None
		try:
			cached_data = cache.read_bytes()
			if time.time() - cache.stat().st_mtime < 86400:
				ranking = cls._parse_popularity_ranking(cached_data)
				if ranking:
					return ranking
		except (OSError, EOFError, gzip.BadGzipFile, ValueError):
			cached_data = None

		try:
			request = Request(POPULARITY_URL, headers={"User-Agent": "InvictusOS-Store/1.0"})
			with urlopen(request, timeout=10) as response:
				data = response.read()
			ranking = cls._parse_popularity_ranking(data)
			if not ranking:
				raise ValueError("Popularity data did not contain package rankings.")
			cache.parent.mkdir(parents=True, exist_ok=True)
			cache.write_bytes(data)
			return ranking
		except (OSError, EOFError, gzip.BadGzipFile, ValueError):
			if cached_data:
				ranking = cls._parse_popularity_ranking(cached_data)
				if ranking:
					return ranking
			raise

	@staticmethod
	def _populate_tree(tree: ttk.Treeview, packages) -> int:
		tree.delete(*tree.get_children())
		count = 0
		for package in packages:
			if count >= AptStore.MAX_VISIBLE_PACKAGES:
				break
			tree.insert("", "end", iid=package.name, values=(package.name, package.summary))
			count += 1
		return count

	def _tab_changed(self, _event: tk.Event) -> None:
		selected_tab = self.tabs.select()
		if selected_tab == str(self.installed_tab):
			current_view = "installed"
		elif selected_tab == str(self.popular_tab):
			current_view = "popular"
		elif selected_tab == str(self.tools_tab):
			current_view = "tools"
		else:
			current_view = "explore"
		if getattr(self, "selected_view", "") != current_view:
			self.selected_name = None
			self.selected_view = ""
			self.selected_package = None
		if current_view == "installed":
			self._load_installed()
			self._filter_installed()
		elif current_view == "popular":
			self._load_popular()
		self.action_button.configure(text="Install")
		self._update_action_button()

	def _select_explore_package(self, name: str) -> None:
		if not self.explore_tree.exists(name):
			return
		self.explore_tree.selection_set(name)
		self.explore_tree.focus(name)
		self.explore_tree.see(name)
		self._selection_changed("explore")

	def _selection_changed(self, view: str) -> None:
		tree = {
			"popular": self.popular_tree,
			"explore": self.explore_tree,
			"installed": self.installed_tree,
		}[view]
		selection = tree.selection()
		if not selection:
			return
		name = selection[0]
		if view == "popular":
			package = self.popular_packages.get(name)
		elif view == "explore":
			package = self.packages.get(name)
		else:
			package = next((item for item in self.installed_packages if item.name == name), None)
		if package is None:
			return
		heading = getattr(self, f"{view}_heading")
		details = getattr(self, f"{view}_details")
		self.selected_name = name
		self.selected_view = view
		self.selected_package = package
		heading.configure(text=name)
		self._set_package_metadata(details, package.version or "Loading…", "Loading…")
		self._set_text(details, package.summary + "\n\nLoading package details…")
		self._update_action_button()
		self._load_package_details(name, view, package)

	def _load_package_details(self, name: str, view: str, package: Package) -> None:
		if not shutil.which("apt-cache"):
			self._set_package_metadata(
				getattr(self, f"{view}_details"), package.version or "Unknown", "Unavailable"
			)
			return

		def work(progress: Callable[[int], None]) -> str:
			progress(5)
			output = self._command(["apt-cache", "show", name])
			progress(90)
			return output

		def done(result: object, error: Exception | None) -> None:
			if self.selected_name != name or self.selected_view != view:
				return
			details = getattr(self, f"{view}_details")
			if error:
				self._set_package_metadata(
					details, package.version or "Unknown", "Unavailable"
				)
				return
			paragraphs = str(result).split("\n\n")
			fields: dict[str, str] = {}
			current_field = ""
			for line in paragraphs[0].splitlines():
				if line[:1].isspace() and current_field:
					fields[current_field] += "\n" + line.strip()
				elif ": " in line:
					current_field, value = line.split(": ", 1)
					fields[current_field] = value
			package.version = fields.get("Version", package.version)
			package.section = fields.get("Section", package.section)
			package.section_loaded = True
			package.description = fields.get("Description", package.summary)
			package.summary = package_summary(package.description, package.summary)
			self._set_package_metadata(
				details,
				package.version or "Unknown",
				fields.get("Section", package.section or "Unknown"),
			)
			self._set_text(details, package.description or package.summary)

		self._run_background(work, done)

	@staticmethod
	def _resize_description(event: tk.Event) -> None:
		AptStore._layout_description(event.widget, event.width, event.height)

	@staticmethod
	def _layout_description(widget: tk.Canvas, width: int, height: int) -> None:
		text_width = max(80, width - 24)
		widget.itemconfigure("description", width=text_width)
		description_y = 12
		if widget.itemcget("version_box", "state") != "hidden":
			version_bottom = AptStore._layout_metadata_box(
				widget, "version_box", "version_label", "version_value", 12, width
			)
			section_y = version_bottom + 8
			section_bottom = AptStore._layout_metadata_box(
				widget, "section_box", "section_label", "section_value", section_y, width
			)
			description_y = section_bottom + 16
		widget.coords("description", 12, description_y)
		bounds = widget.bbox("description")
		bottom = bounds[3] + 16 if bounds else height
		widget.configure(scrollregion=(0, 0, width, max(height, bottom)))

	@staticmethod
	def _layout_metadata_box(
		widget: tk.Canvas,
		box_tag: str,
		label_tag: str,
		value_tag: str,
		y: int,
		width: int,
	) -> int:
		left = 12
		box_width = max(1, width - 24)
		widget.itemconfigure(value_tag, width=max(60, box_width - 20))
		widget.coords(label_tag, left + 10, y + 8)
		widget.coords(value_tag, left + 10, y + 24)
		value_bounds = widget.bbox(value_tag)
		bottom = max(y + 48, value_bounds[3] + 8 if value_bounds else y + 48)
		widget.coords(box_tag, left, y, left + box_width, bottom)
		return bottom

	@classmethod
	def _set_package_metadata(
		cls, widget: tk.Canvas, version: str, section: str
	) -> None:
		widget.itemconfigure("version_value", text=version)
		widget.itemconfigure("section_value", text=section)
		for tag in (
			"version_box",
			"version_label",
			"version_value",
			"section_box",
			"section_label",
			"section_value",
		):
			widget.itemconfigure(tag, state="normal")
		cls._layout_description(widget, widget.winfo_width(), widget.winfo_height())

	@classmethod
	def _set_text(cls, widget: tk.Canvas, value: str) -> None:
		widget.itemconfigure("description", text=value)
		cls._layout_description(widget, widget.winfo_width(), widget.winfo_height())
		widget.yview_moveto(0)

	def _action_state(self) -> str:
		name = getattr(self, "selected_name", None)
		return "normal" if name else "disabled"

	def _update_action_button(self) -> None:
		name = getattr(self, "selected_name", None)
		if not name:
			self.action_button.configure(state="disabled")
			return
		package = getattr(self, "selected_package", None)
		label = package_action_label(package)
		is_negative = package_status_is_negative("remove" if package and package.installed else "install", True)
		self.action_button.configure(
			text=label,
			background=self.COLOR_ERROR if is_negative else self.COLOR_SUBTITLE,
			foreground=self.COLOR_BACKGROUND if is_negative else self.COLOR_BACKGROUND,
			hover_background=self.COLOR_ERROR if is_negative else self.COLOR_ACCENT_TEXT,
			state="disabled" if self.busy else "normal",
		)

	def _change_package_state(self) -> None:
		name = getattr(self, "selected_name", None)
		if not name or self.busy:
			return
		if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?", name):
			self._show_error("The selected package name is not valid.")
			return
		package = getattr(self, "selected_package", None)
		remove = bool(package and package.installed)
		operation = "remove" if remove else "install"
		if not shutil.which("pkexec"):
			self._show_error(
				"Graphical administrator authorization (pkexec) is unavailable. "
				"Install PolicyKit on Debian to manage packages from this app."
			)
			return
		if not messagebox.askyesno(
			f"{operation.title()} {name}?",
			f"APT will {operation} {name} and may also change its dependencies.",
			parent=self.root,
		):
			return

		self._set_busy(True, f"Waiting for authorization to {operation} {name}…")
		args = ["pkexec", "apt-get", "-y", "--show-progress", operation, "--", name]

		def work(progress: Callable[[int], None]) -> str:
			progress(5)
			return self._command(args, timeout=3600, progress=progress)

		self._run_background(
			work,
			lambda result, error: self._operation_finished(operation, name, error),
			priority=True,
		)

	def _operation_finished(self, operation: str, name: str, error: Exception | None) -> None:
		self._set_busy(False)
		if error:
			self._show_error(f"APT could not {operation} {name}:\n{error}")
			self._set_status(
				package_operation_status(operation, name, False),
				error=package_status_is_negative(operation, False),
			)
			return
		status = package_operation_status(operation, name, True)
		self._set_status(
			status,
			error=package_status_is_negative(operation, True),
		)
		messagebox.showinfo(
			"Package update",
			status,
			parent=self.root,
		)
		self.selected_name = None
		self.selected_view = ""
		self.selected_package = None
		self._update_action_button()
		self.installed_loaded = False
		self.popular_loaded = False
		self._load_installed()
		if operation == "install":
			self.tabs.select(self.installed_tab)
		else:
			package = self.popular_packages.get(name) or self.packages.get(name) or next(
				(item for item in self.installed_packages if item.name == name),
				Package(name, name),
			)
			package.installed = False
			self.packages[name] = package
			if not self.explore_tree.exists(name):
				self.explore_tree.insert("", "end", iid=name, values=(name, package.summary))
			self.tabs.select(self.explore_tab)
			self.root.after_idle(lambda: self._select_explore_package(name))

	def _refresh_lists(self) -> None:
		if not shutil.which("pkexec") or not shutil.which("apt-get"):
			self._show_error("Refreshing package lists requires APT and graphical authorization (pkexec).")
			return
		self._set_busy(True, "Refreshing package lists…")

		def work(progress: Callable[[int], None]) -> str:
			progress(5)
			return self._command(["pkexec", "apt-get", "update"], timeout=3600)

		def done(_result: object, error: Exception | None) -> None:
			self._set_busy(False)
			if error:
				self._show_error(f"Could not refresh package lists:\n{error}")
				self._set_status("Package list refresh failed.", error=True)
			else:
				self._set_status("Package lists refreshed. Search to see the latest packages.")

		self._run_background(work, done)

	def _show_error(self, text: str) -> None:
		self._set_status(text.splitlines()[0], error=True)
		messagebox.showerror("InvictusOS Store", text, parent=self.root)


def main() -> None:
	root = tk.Tk()
	AptStore(root)
	root.mainloop()


if __name__ == "__main__":
	main()


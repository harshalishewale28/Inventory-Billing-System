from __future__ import annotations

import datetime as dt
import os
import platform
import re
import shutil
import subprocess
import tkinter as tk
import calendar
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from tkinter_billing_system.database import APP_DIR, DatabaseManager
from tkinter_billing_system.reports import export_bill_pdf, export_simple_report


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GRADIENT_TOP = "#6495ED"
GRADIENT_BOTTOM = "#FFFFFF"
CARD_BG = "#FDFDFD"
TITLE_FG = "#191970"
LABEL_FG = "#243447"


def open_system_app(*, macos_app: str, windows_commands: list[str], linux_commands: list[str]) -> None:
    system = platform.system()

    if system == "Darwin":
        subprocess.Popen(["open", "-a", macos_app])
        return

    if system == "Windows":
        for command in windows_commands:
            if shutil.which(command):
                subprocess.Popen([command])
                return
        raise FileNotFoundError(f"No supported Windows command found for {macos_app}.")

    if system == "Linux":
        for command in linux_commands:
            if shutil.which(command):
                subprocess.Popen([command])
                return
        raise FileNotFoundError(f"No supported Linux command found for {macos_app}.")

    raise OSError(f"Unsupported operating system: {system}")


def draw_vertical_gradient(canvas: tk.Canvas, width: int, height: int, color1: str, color2: str) -> None:
    canvas.delete("gradient")
    r1, g1, b1 = [value // 256 for value in canvas.winfo_rgb(color1)]
    r2, g2, b2 = [value // 256 for value in canvas.winfo_rgb(color2)]
    steps = max(height, 1)
    for i in range(steps):
        ratio = i / steps
        nr = int(r1 + (r2 - r1) * ratio)
        ng = int(g1 + (g2 - g1) * ratio)
        nb = int(b1 + (b2 - b1) * ratio)
        color = f"#{nr:02x}{ng:02x}{nb:02x}"
        canvas.create_line(0, i, width, i, tags=("gradient",), fill=color)
    canvas.lower("gradient")


class GradientWindow:
    def build_shell(self, width: int, height: int, title: str):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        safe_width = min(width, max(screen_width - 80, 640))
        safe_height = min(height, max(screen_height - 80, 420))
        min_width = min(safe_width, max(safe_width - 120, 640))
        min_height = min(safe_height, max(safe_height - 120, 420))

        self.title(title)
        self.geometry(f"{safe_width}x{safe_height}")
        self.minsize(min_width, min_height)
        self.configure(bg=GRADIENT_BOTTOM)

        outer = tk.Frame(self, bg=GRADIENT_BOTTOM)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        card = tk.Frame(canvas, bg=CARD_BG, bd=1, relief="flat")
        header = tk.Label(card, text=title, bg=CARD_BG, fg=TITLE_FG, font=("Helvetica", 26, "bold"))
        header.pack(pady=(18, 10))
        body = tk.Frame(card, bg=CARD_BG)
        body.pack(fill="both", expand=True, padx=22, pady=(0, 20))

        window_id = canvas.create_window(20, 20, anchor="nw", window=card)

        def update_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_mousewheel(event):
            if canvas.winfo_height() < card.winfo_reqheight() + 40:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        card.bind("<Configure>", update_scrollregion)

        def bind_mousewheel(_event):
            canvas.bind_all("<MouseWheel>", on_mousewheel)

        def unbind_mousewheel(_event):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", bind_mousewheel)
        canvas.bind("<Leave>", unbind_mousewheel)
        card.bind("<Enter>", bind_mousewheel)
        card.bind("<Leave>", unbind_mousewheel)

        def on_resize(event):
            draw_vertical_gradient(canvas, event.width, event.height, GRADIENT_TOP, GRADIENT_BOTTOM)
            card_width = max(event.width - 56, min_width - 40)
            canvas.coords(window_id, 20, 20)
            canvas.itemconfigure(window_id, width=card_width)
            update_scrollregion()

        canvas.bind("<Configure>", on_resize)
        return body


class StyledAppMixin:
    def configure_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=28, font=("Helvetica", 11))
        style.configure("Treeview.Heading", font=("Helvetica", 11, "bold"))
        style.configure("TButton", font=("Helvetica", 11, "bold"))
        style.configure("Primary.TButton", font=("Helvetica", 11, "bold"), foreground="white", background="#4682C8", borderwidth=1)
        style.map("Primary.TButton", background=[("active", "#3568A3")], foreground=[("active", "white")])
        style.configure("Neutral.TButton", font=("Helvetica", 11, "bold"), foreground="white", background="#8A8F98", borderwidth=1)
        style.map("Neutral.TButton", background=[("active", "#737983")], foreground=[("active", "white")])
        style.configure("TLabel", background=CARD_BG, font=("Helvetica", 11))
        style.configure("TFrame", background=CARD_BG)
        style.configure("TLabelframe", background=CARD_BG)
        style.configure("TLabelframe.Label", background=CARD_BG, font=("Helvetica", 12, "bold"))


def make_label(parent, text: str, *, width: int | None = None, bold: bool = False, bg: str = CARD_BG) -> tk.Label:
    font = ("Helvetica", 12, "bold" if bold else "normal")
    options = {"text": text, "bg": bg, "fg": LABEL_FG, "font": font, "anchor": "w"}
    if width is not None:
        options["width"] = width
    return tk.Label(parent, **options)


def format_stock(value) -> str:
    amount = float(value or 0)
    return str(int(amount)) if amount.is_integer() else f"{amount:.2f}"


class BillingApp(tk.Tk, StyledAppMixin):
    def __init__(self) -> None:
        super().__init__()
        self.db = DatabaseManager()
        self.current_user = "admin"
        self.configure_style()
        self.title("Inventory and Billing System")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        width = min(1369, max(screen_width - 80, 900))
        height = min(750, max(screen_height - 80, 620))
        self.geometry(f"{width}x{height}")
        self.minsize(min(width, 900), min(height, 620))
        self.login_frame = LoginFrame(self, self.on_login_success)
        self.login_frame.pack(fill="both", expand=True)
        self.main_shell: MainShell | None = None

    def on_login_success(self, username: str) -> None:
        self.current_user = username
        self.login_frame.destroy()
        self.main_shell = MainShell(self, self.db, username)
        self.main_shell.pack(fill="both", expand=True)


class LoginFrame(tk.Frame):
    def __init__(self, master: BillingApp, on_success) -> None:
        super().__init__(master, bg=GRADIENT_BOTTOM)
        self.db = master.db
        self.on_success = on_success
        canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        card = tk.Frame(canvas, bg="#FFFFFF", padx=32, pady=28)
        title = tk.Label(card, text="Login to Inventory and Billing System", bg="#FFFFFF", fg=TITLE_FG, font=("Helvetica", 20, "bold"))
        title.grid(row=0, column=0, columnspan=2, pady=(0, 18))
        make_label(card, "Username:", width=12, bg="#FFFFFF").grid(row=1, column=0, sticky="w", pady=10)
        make_label(card, "Password:", width=12, bg="#FFFFFF").grid(row=2, column=0, sticky="w", pady=10)
        self.username = tk.StringVar(value="admin")
        self.password = tk.StringVar(value="admin")
        ttk.Entry(card, textvariable=self.username, width=28).grid(row=1, column=1, pady=10, padx=(10, 0))
        password_entry = ttk.Entry(card, textvariable=self.password, width=28, show="*")
        password_entry.grid(row=2, column=1, pady=10, padx=(10, 0))
        ttk.Button(card, text="Login", command=self.attempt_login).grid(row=3, column=0, pady=(18, 0))
        ttk.Button(card, text="Cancel", command=master.destroy).grid(row=3, column=1, pady=(18, 0))
        window_id = canvas.create_window(0, 0, anchor="center", window=card)

        def on_resize(event):
            draw_vertical_gradient(canvas, event.width, event.height, GRADIENT_TOP, GRADIENT_BOTTOM)
            canvas.coords(window_id, event.width / 2, event.height / 2)

        canvas.bind("<Configure>", on_resize)
        password_entry.bind("<Return>", lambda _e: self.attempt_login())

    def attempt_login(self) -> None:
        if self.db.authenticate_user(self.username.get().strip(), self.password.get()):
            self.on_success(self.username.get().strip())
            return
        messagebox.showerror("Login Failed", "Invalid username or password.")


class MainShell(tk.Frame):
    def __init__(self, master: BillingApp, db: DatabaseManager, username: str) -> None:
        super().__init__(master, bg=GRADIENT_BOTTOM)
        self.master = master
        self.db = db
        self.username = username
        self.open_windows: list[tk.Toplevel] = []

        self.menu = tk.Menu(master)
        master.config(menu=self.menu)
        self._build_menu()

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.welcome = tk.Label(
            self.canvas,
            text="Inventory and Billing System",
            bg=GRADIENT_BOTTOM,
            fg=TITLE_FG,
            font=("Helvetica", 24, "bold"),
        )
        self.subtitle = tk.Label(
            self.canvas,
            text=f"Logged in as {username}",
            bg=GRADIENT_BOTTOM,
            fg="#2F4F4F",
            font=("Helvetica", 13),
        )
        self.canvas.bind("<Configure>", self._render)

    def _render(self, event=None) -> None:
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        draw_vertical_gradient(self.canvas, width, height, GRADIENT_TOP, GRADIENT_BOTTOM)
        self.canvas.delete("welcome_text")
        self.canvas.create_text(width / 2, height / 2 - 10, text="Inventory and Billing System", fill=TITLE_FG, font=("Helvetica", 30, "bold"), tags="welcome_text")
        self.canvas.create_text(width / 2, height / 2 + 30, text=f"User: {self.username}", fill="#2F4F4F", font=("Helvetica", 15), tags="welcome_text")

    def _build_menu(self) -> None:
        add_menu = tk.Menu(self.menu, tearoff=0)
        add_menu.add_command(label="Add Customer", accelerator="Ctrl+C", command=lambda: CustomerWindow(self.master, self.db, mode="add", on_change=self.refresh_all))
        add_menu.add_command(label="Add Items", accelerator="Ctrl+I", command=lambda: ItemWindow(self.master, self.db, mode="add", on_change=self.refresh_all))
        add_menu.add_command(label="Billing", accelerator="Ctrl+B", command=lambda: BillingWindow(self.master, self.db, on_change=self.refresh_all))
        self.menu.add_cascade(label="Add", menu=add_menu)

        view_menu = tk.Menu(self.menu, tearoff=0)
        view_menu.add_command(label="Customers", accelerator="Alt+C", command=lambda: CustomerWindow(self.master, self.db, mode="view", on_change=self.refresh_all))
        view_menu.add_command(label="Items", accelerator="Alt+I", command=lambda: ItemWindow(self.master, self.db, mode="view", on_change=self.refresh_all))
        view_menu.add_command(label="Search Customer", command=lambda: CustomerWindow(self.master, self.db, mode="search", on_change=self.refresh_all))
        view_menu.add_command(label="Search Item", command=lambda: ItemWindow(self.master, self.db, mode="search", on_change=self.refresh_all))
        view_menu.add_command(label="Bills", command=lambda: BillsWindow(self.master, self.db))
        self.menu.add_cascade(label="View", menu=view_menu)

        edit_menu = tk.Menu(self.menu, tearoff=0)
        edit_menu.add_command(label="Edit Customers", command=lambda: CustomerWindow(self.master, self.db, mode="edit", on_change=self.refresh_all))
        edit_menu.add_command(label="Edit Items", command=lambda: ItemWindow(self.master, self.db, mode="edit", on_change=self.refresh_all))
        self.menu.add_cascade(label="Edit", menu=edit_menu)

        tools_menu = tk.Menu(self.menu, tearoff=0)
        tools_menu.add_command(label="Calculator", command=self.open_calculator)
        tools_menu.add_command(label="Notepad", command=self.open_notepad)
        self.menu.add_cascade(label="Tools", menu=tools_menu)

        settings_menu = tk.Menu(self.menu, tearoff=0)
        settings_menu.add_command(label="Change Username / Password", command=lambda: SettingsWindow(self, self.db, self.username))
        self.menu.add_cascade(label="Setting", menu=settings_menu)

        report_menu = tk.Menu(self.menu, tearoff=0)
        report_menu.add_command(label="All Customers", command=lambda: export_all_customers(self.db))
        report_menu.add_command(label="Single Customer", command=lambda: export_single_customer(self.db))
        report_menu.add_command(label="All Items", command=lambda: export_all_items(self.db))
        report_menu.add_command(label="All Sales", command=lambda: export_sales(self.db))
        report_menu.add_command(label="Bill", command=lambda: export_selected_bill(self.db))
        self.menu.add_cascade(label="Report", menu=report_menu)

        help_menu = tk.Menu(self.menu, tearoff=0)
        help_menu.add_command(label="About", command=lambda: AboutWindow(self.master))
        self.menu.add_cascade(label="Help", menu=help_menu)

        alerts_menu = tk.Menu(self.menu, tearoff=0)
        alerts_menu.add_command(label="Show Alerts", command=lambda: AlertsWindow(self.master, self.db))
        self.menu.add_cascade(label="Alerts", menu=alerts_menu)

    def open_calculator(self) -> None:
        try:
            open_system_app(
                macos_app="Calculator",
                windows_commands=["calc"],
                linux_commands=["gnome-calculator", "kcalc", "mate-calc", "galculator", "xcalc"],
            )
        except Exception as exc:
            messagebox.showerror("Calculator", f"Could not open Calculator.\n{exc}")

    def open_notepad(self) -> None:
        try:
            if platform.system() == "Windows":
                os.startfile("notepad.exe")
            else:
                open_system_app(
                    macos_app="TextEdit",
                    windows_commands=["notepad"],
                    linux_commands=["gedit", "kate", "mousepad", "leafpad", "pluma", "xed", "nano"],
                )
        except Exception as exc:
            messagebox.showerror("Notepad", f"Could not open the text editor.\n{exc}")

    def refresh_all(self) -> None:
        pass


class BaseChildWindow(tk.Toplevel, GradientWindow, StyledAppMixin):
    def __init__(self, master, title: str, width: int, height: int) -> None:
        super().__init__(master)
        self.configure_style()
        self.body = self.build_shell(width, height, title)
        self.transient(master)

    def add_button_bar(self, parent, buttons: list[tuple[str, callable]]) -> None:
        row = tk.Frame(parent, bg=CARD_BG)
        row.pack(fill="x", pady=(10, 0))
        for index, (text, command) in enumerate(buttons):
            row.grid_columnconfigure(index, weight=1)
            ttk.Button(row, text=text, command=command).grid(row=0, column=index, padx=8, sticky="ew")


class DatePickerPopup(tk.Toplevel):
    def __init__(self, master, target_var: tk.StringVar, initial_date: str = "") -> None:
        super().__init__(master)
        self.target_var = target_var
        self.configure(bg=CARD_BG)
        self.resizable(False, False)
        self.title("Select Date")
        self.transient(master)
        self.grab_set()

        try:
            selected = dt.date.fromisoformat(initial_date.strip()) if initial_date.strip() else dt.date.today()
        except ValueError:
            selected = dt.date.today()

        self.current_year = selected.year
        self.current_month = selected.month
        self.selected_day = selected.day

        container = tk.Frame(self, bg=CARD_BG, padx=12, pady=12)
        container.pack(fill="both", expand=True)

        header = tk.Frame(container, bg=CARD_BG)
        header.pack(fill="x", pady=(0, 8))
        ttk.Button(header, text="<", width=3, command=self.prev_month).pack(side="left")
        self.title_label = tk.Label(header, bg=CARD_BG, fg=TITLE_FG, font=("Helvetica", 13, "bold"))
        self.title_label.pack(side="left", expand=True)
        ttk.Button(header, text=">", width=3, command=self.next_month).pack(side="right")

        self.days_frame = tk.Frame(container, bg=CARD_BG)
        self.days_frame.pack()

        footer = tk.Frame(container, bg=CARD_BG)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Button(footer, text="Today", command=self.pick_today).pack(side="left")
        ttk.Button(footer, text="Clear", command=self.clear_date).pack(side="left", padx=8)
        ttk.Button(footer, text="Close", command=self.destroy).pack(side="right")

        self.render_calendar()

    def render_calendar(self) -> None:
        for child in self.days_frame.winfo_children():
            child.destroy()

        self.title_label.config(text=f"{calendar.month_name[self.current_month]} {self.current_year}")

        for idx, day_name in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
            tk.Label(
                self.days_frame,
                text=day_name,
                bg=CARD_BG,
                fg=LABEL_FG,
                font=("Helvetica", 10, "bold"),
                width=4,
            ).grid(row=0, column=idx, padx=2, pady=(0, 4))

        month_matrix = calendar.monthcalendar(self.current_year, self.current_month)
        for row_index, week in enumerate(month_matrix, start=1):
            for col_index, day in enumerate(week):
                if day == 0:
                    tk.Label(self.days_frame, text="", bg=CARD_BG, width=4).grid(row=row_index, column=col_index, padx=2, pady=2)
                    continue
                date_text = f"{self.current_year:04d}-{self.current_month:02d}-{day:02d}"
                style = "Primary.TButton" if self._is_selected(day) else "TButton"
                ttk.Button(
                    self.days_frame,
                    text=str(day),
                    width=4,
                    style=style,
                    command=lambda value=date_text: self.select_date(value),
                ).grid(row=row_index, column=col_index, padx=2, pady=2)

    def _is_selected(self, day: int) -> bool:
        return (
            self.target_var.get() == f"{self.current_year:04d}-{self.current_month:02d}-{day:02d}"
        )

    def prev_month(self) -> None:
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self.render_calendar()

    def next_month(self) -> None:
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self.render_calendar()

    def select_date(self, value: str) -> None:
        self.target_var.set(value)
        self.destroy()

    def pick_today(self) -> None:
        self.select_date(dt.date.today().isoformat())

    def clear_date(self) -> None:
        self.target_var.set("")
        self.destroy()


class CustomerWindow(BaseChildWindow):
    def __init__(self, master, db: DatabaseManager, mode: str, on_change) -> None:
        title_map = {"add": "ADD CUSTOMER DETAILS", "view": "CUSTOMER DETAILS", "search": "SEARCH CUSTOMER", "edit": "EDIT CUSTOMER DETAILS"}
        super().__init__(master, title_map[mode], 980, 680)
        self.db = db
        self.mode = mode
        self.on_change = on_change
        self.selected_id: int | None = None
        self.search_name = tk.StringVar()
        self.search_id = tk.StringVar()
        self.fields = {name: tk.StringVar() for name in ["name", "address1", "address2", "address3", "phone", "email", "cst_no", "tin_no", "stex_no"]}
        top = tk.Frame(self.body, bg=CARD_BG)
        top.pack(fill="both", expand=True)
        if mode in {"add", "edit"}:
            form_frame = tk.Frame(top, bg=CARD_BG)
            form_frame.pack(side="left", fill="y", padx=(0, 18))
            self._build_form(form_frame)
        list_frame = tk.Frame(top, bg=CARD_BG)
        list_frame.pack(side="left", fill="both", expand=True)
        self._build_list(list_frame)
        self.refresh()

    def _build_form(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)
        for idx, (label, key) in enumerate([
            ("Customer Name:", "name"),
            ("Address Line 1:", "address1"),
            ("Address Line 2:", "address2"),
            ("Address Line 3:", "address3"),
            ("Phone No.:", "phone"),
            ("Email ID:", "email"),
            ("CST No.:", "cst_no"),
            ("TIN No.:", "tin_no"),
            ("STEX No.:", "stex_no"),
        ]):
            make_label(parent, label, width=16).grid(row=idx, column=0, sticky="w", pady=7)
            ttk.Entry(parent, textvariable=self.fields[key], width=30).grid(row=idx, column=1, padx=(10, 0), pady=7, sticky="ew")
        buttons = tk.Frame(parent, bg=CARD_BG)
        buttons.grid(row=10, column=0, columnspan=2, pady=(18, 0))
        for col in range(2):
            buttons.grid_columnconfigure(col, weight=1)
        ttk.Button(buttons, text="SAVE", command=self.save).grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        if self.mode == "edit":
            ttk.Button(buttons, text="DELETE", command=self.delete_selected).grid(row=0, column=1, padx=6, pady=6, sticky="ew")
            ttk.Button(buttons, text="CLEAR", command=self.clear_form).grid(row=1, column=0, padx=6, pady=6, sticky="ew")
            ttk.Button(buttons, text="EXIT", command=self.destroy).grid(row=1, column=1, padx=6, pady=6, sticky="ew")
        else:
            ttk.Button(buttons, text="CLEAR", command=self.clear_form).grid(row=0, column=1, padx=6, pady=6, sticky="ew")
            ttk.Button(buttons, text="EXIT", command=self.destroy).grid(row=1, column=0, columnspan=2, padx=6, pady=6, sticky="ew")

    def _build_list(self, parent) -> None:
        search_row = tk.Frame(parent, bg=CARD_BG)
        search_row.pack(fill="x", pady=(0, 10))
        make_label(search_row, "Search by Customer Name:", width=22).pack(side="left")
        entry_name = ttk.Entry(search_row, textvariable=self.search_name, width=20)
        entry_name.pack(side="left", padx=8)
        make_label(search_row, "Search by Customer No:", width=18).pack(side="left", padx=(10, 0))
        entry_id = ttk.Entry(search_row, textvariable=self.search_id, width=12)
        entry_id.pack(side="left", padx=8)
        entry_name.bind("<KeyRelease>", lambda _e: self.refresh())
        entry_id.bind("<KeyRelease>", lambda _e: self.refresh())
        cols = ("id", "name", "phone", "email", "cst_no", "tin_no")
        self.tree = ttk.Treeview(parent, columns=cols, show="headings", height=16)
        for col, width in zip(cols, [70, 190, 120, 200, 100, 100]):
            self.tree.heading(col, text=col.replace("_", " ").title())
            self.tree.column(col, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

    def refresh(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        search_text = self.search_name.get().strip().lower()
        search_id = self.search_id.get().strip()
        rows = self.db.list_customers()
        for row in rows:
            if search_text and search_text not in row["name"].lower():
                continue
            if search_id and search_id not in str(row["id"]):
                continue
            self.tree.insert("", "end", values=(row["id"], row["name"], row["phone"], row["email"], row["cst_no"], row["tin_no"]))

    def on_select(self, _event=None) -> None:
        if not self.tree.selection():
            return
        values = self.tree.item(self.tree.selection()[0], "values")
        customer = self.db.get_customer(int(values[0]))
        if not customer:
            return
        self.selected_id = customer["id"]
        if self.mode in {"add", "edit"}:
            for key in self.fields:
                self.fields[key].set(customer[key])

    def validate(self) -> bool:
        name = self.fields["name"].get().strip()
        phone = self.fields["phone"].get().strip()
        email = self.fields["email"].get().strip()
        if not name:
            messagebox.showerror("Validation Error", "Customer name is required.", parent=self)
            return False
        if any(ch.isdigit() for ch in name):
            messagebox.showerror("Validation Error", "Customer name cannot contain digits.", parent=self)
            return False
        if not phone.isdigit() or not 6 <= len(phone) <= 10:
            messagebox.showerror("Validation Error", "Phone number must be 6 to 10 digits.", parent=self)
            return False
        if email and not EMAIL_RE.match(email):
            messagebox.showerror("Validation Error", "Please enter a valid email address.", parent=self)
            return False
        for key in ("cst_no", "tin_no", "stex_no"):
            value = self.fields[key].get().strip()
            if value and not value.isdigit():
                messagebox.showerror("Validation Error", f"{key.replace('_', ' ').upper()} must contain only digits.", parent=self)
                return False
        return True

    def save(self) -> None:
        if not self.validate():
            return
        payload = {key: var.get().strip() for key, var in self.fields.items()}
        if self.mode == "edit" and self.selected_id:
            payload["id"] = self.selected_id
        self.db.upsert_customer(payload)
        self.on_change()
        self.refresh()
        self.clear_form()
        messagebox.showinfo("Saved", "Customer record saved successfully.", parent=self)

    def delete_selected(self) -> None:
        if not self.selected_id:
            messagebox.showerror("Delete", "Select a customer first.", parent=self)
            return
        try:
            self.db.delete_customer(self.selected_id)
        except ValueError as exc:
            messagebox.showerror("Delete Blocked", str(exc), parent=self)
            return
        self.on_change()
        self.refresh()
        self.clear_form()

    def clear_form(self) -> None:
        self.selected_id = None
        for var in self.fields.values():
            var.set("")


class ItemWindow(BaseChildWindow):
    def __init__(self, master, db: DatabaseManager, mode: str, on_change) -> None:
        title_map = {"add": "ADD ITEM DETAILS", "view": "ITEM DETAILS", "search": "SEARCH ITEMS", "edit": "EDIT ITEM DETAILS"}
        super().__init__(master, title_map[mode], 980, 650)
        self.db = db
        self.mode = mode
        self.on_change = on_change
        self.selected_id: int | None = None
        self.search_name = tk.StringVar()
        self.search_id = tk.StringVar()
        self.fields = {name: tk.StringVar() for name in ["name", "make_name", "rate", "ratio", "stock", "unit"]}
        top = tk.Frame(self.body, bg=CARD_BG)
        top.pack(fill="both", expand=True)
        if mode in {"add", "edit"}:
            form_frame = tk.Frame(top, bg=CARD_BG)
            form_frame.pack(side="left", fill="y", padx=(0, 18))
            self._build_form(form_frame)
        list_frame = tk.Frame(top, bg=CARD_BG)
        list_frame.pack(side="left", fill="both", expand=True)
        self._build_list(list_frame)
        self.refresh()

    def _build_form(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)
        for idx, (label, key) in enumerate([
            ("Item Name:", "name"),
            ("Item Make:", "make_name"),
            ("Item Rate:", "rate"),
            ("Item Ratio:", "ratio"),
            ("Stock:", "stock"),
            ("Item Unit:", "unit"),
        ]):
            make_label(parent, label, width=14).grid(row=idx, column=0, sticky="w", pady=8)
            ttk.Entry(parent, textvariable=self.fields[key], width=30).grid(row=idx, column=1, padx=(10, 0), pady=8, sticky="ew")
        buttons = tk.Frame(parent, bg=CARD_BG)
        buttons.grid(row=7, column=0, columnspan=2, pady=(18, 0))
        for col in range(2):
            buttons.grid_columnconfigure(col, weight=1)
        ttk.Button(buttons, text="SAVE", command=self.save).grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        if self.mode == "edit":
            ttk.Button(buttons, text="DELETE", command=self.delete_selected).grid(row=0, column=1, padx=6, pady=6, sticky="ew")
            ttk.Button(buttons, text="CLEAR", command=self.clear_form).grid(row=1, column=0, padx=6, pady=6, sticky="ew")
            ttk.Button(buttons, text="EXIT", command=self.destroy).grid(row=1, column=1, padx=6, pady=6, sticky="ew")
        else:
            ttk.Button(buttons, text="CLEAR", command=self.clear_form).grid(row=0, column=1, padx=6, pady=6, sticky="ew")
            ttk.Button(buttons, text="EXIT", command=self.destroy).grid(row=1, column=0, columnspan=2, padx=6, pady=6, sticky="ew")

    def _build_list(self, parent) -> None:
        search_row = tk.Frame(parent, bg=CARD_BG)
        search_row.pack(fill="x", pady=(0, 10))
        make_label(search_row, "Search by Item Name:", width=18).pack(side="left")
        entry_name = ttk.Entry(search_row, textvariable=self.search_name, width=20)
        entry_name.pack(side="left", padx=8)
        make_label(search_row, "Search by Item No:", width=16).pack(side="left", padx=(10, 0))
        entry_id = ttk.Entry(search_row, textvariable=self.search_id, width=12)
        entry_id.pack(side="left", padx=8)
        entry_name.bind("<KeyRelease>", lambda _e: self.refresh())
        entry_id.bind("<KeyRelease>", lambda _e: self.refresh())
        cols = ("id", "name", "make", "rate", "ratio", "stock", "unit")
        self.tree = ttk.Treeview(parent, columns=cols, show="headings", height=16)
        for col, width in zip(cols, [70, 180, 140, 90, 90, 90, 90]):
            self.tree.heading(col, text=col.title())
            self.tree.column(col, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

    def refresh(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        search_text = self.search_name.get().strip().lower()
        search_id = self.search_id.get().strip()
        for row in self.db.list_items():
            if search_text and search_text not in row["name"].lower():
                continue
            if search_id and search_id not in str(row["id"]):
                continue
            self.tree.insert("", "end", values=(row["id"], row["name"], row["make_name"], f"{row['rate']:.2f}", f"{row['ratio']:.2f}", format_stock(row["stock"]), row["unit"]))

    def on_select(self, _event=None) -> None:
        if not self.tree.selection():
            return
        values = self.tree.item(self.tree.selection()[0], "values")
        item = self.db.get_item(int(values[0]))
        if not item:
            return
        self.selected_id = item["id"]
        if self.mode in {"add", "edit"}:
            self.fields["name"].set(item["name"])
            self.fields["make_name"].set(item["make_name"])
            self.fields["rate"].set(f"{item['rate']:.2f}")
            self.fields["ratio"].set(f"{item['ratio']:.2f}")
            self.fields["stock"].set(format_stock(item["stock"]))
            self.fields["unit"].set(item["unit"])

    def validate(self) -> bool:
        name = self.fields["name"].get().strip()
        make_name = self.fields["make_name"].get().strip()
        unit = self.fields["unit"].get().strip()
        try:
            rate = float(self.fields["rate"].get())
            ratio = float(self.fields["ratio"].get())
            stock = float(self.fields["stock"].get())
        except ValueError:
            messagebox.showerror("Validation Error", "Rate, ratio, and stock must be numeric.", parent=self)
            return False
        if not name or any(ch.isdigit() for ch in name):
            messagebox.showerror("Validation Error", "Item name is required and cannot contain digits.", parent=self)
            return False
        if make_name and any(ch.isdigit() for ch in make_name):
            messagebox.showerror("Validation Error", "Item make cannot contain digits.", parent=self)
            return False
        if rate <= 0 or ratio <= 0:
            messagebox.showerror("Validation Error", "Rate and ratio must be greater than zero.", parent=self)
            return False
        if stock < 0:
            messagebox.showerror("Validation Error", "Stock cannot be negative.", parent=self)
            return False
        if not unit or any(ch.isdigit() for ch in unit):
            messagebox.showerror("Validation Error", "Item unit is required and cannot contain digits.", parent=self)
            return False
        return True

    def save(self) -> None:
        if not self.validate():
            return
        payload = {
            "name": self.fields["name"].get().strip(),
            "make_name": self.fields["make_name"].get().strip(),
            "rate": float(self.fields["rate"].get()),
            "ratio": float(self.fields["ratio"].get()),
            "stock": float(self.fields["stock"].get()),
            "unit": self.fields["unit"].get().strip(),
        }
        if self.mode == "edit" and self.selected_id:
            payload["id"] = self.selected_id
        self.db.upsert_item(payload)
        self.on_change()
        self.refresh()
        self.clear_form()
        messagebox.showinfo("Saved", "Item record saved successfully.", parent=self)

    def delete_selected(self) -> None:
        if not self.selected_id:
            messagebox.showerror("Delete", "Select an item first.", parent=self)
            return
        try:
            self.db.delete_item(self.selected_id)
        except ValueError as exc:
            messagebox.showerror("Delete Blocked", str(exc), parent=self)
            return
        self.on_change()
        self.refresh()
        self.clear_form()

    def clear_form(self) -> None:
        self.selected_id = None
        for var in self.fields.values():
            var.set("")


class BillingWindow(BaseChildWindow):
    def __init__(self, master, db: DatabaseManager, on_change) -> None:
        super().__init__(master, "BILLING", 1220, 760)
        self.db = db
        self.on_change = on_change
        self.current_cart: list[dict] = []
        self.customer_map: dict[str, int] = {}
        self.selected_item_id: int | None = None
        self.bill_no = tk.StringVar()
        self.bill_date = tk.StringVar(value=dt.date.today().isoformat())
        self.customer_id = tk.StringVar()
        self.cst_no = tk.StringVar()
        self.tin_no = tk.StringVar()
        self.po_no = tk.StringVar()
        self.po_date = tk.StringVar()
        self.tax_percent = tk.StringVar(value="0")
        self.subtotal = tk.StringVar(value="0.00")
        self.tax_amount = tk.StringVar(value="0.00")
        self.total = tk.StringVar(value="0.00")
        self.search_item = tk.StringVar()
        self.item_vars = {name: tk.StringVar() for name in ["item_id", "item_name", "make", "serial", "unit_price", "quantity", "line_total", "unit", "ratio", "stock"]}
        self._build_header()
        self._build_body()
        self.refresh()

    def _build_header(self) -> None:
        header = tk.Frame(self.body, bg=CARD_BG)
        header.pack(fill="x")
        for col in (1, 3, 5):
            header.grid_columnconfigure(col, weight=1)

        pairs = [
            (0, 0, "Bill No:", self.bill_no, "readonly", 16),
            (0, 2, "Date:", self.bill_date, "normal", 16),
            (0, 4, "Bill To:", None, None, 16),
            (1, 0, "Cust No:", self.customer_id, "readonly", 16),
            (1, 2, "CST No:", self.cst_no, "readonly", 16),
            (1, 4, "TIN No:", self.tin_no, "readonly", 16),
            (2, 0, "PO No:", self.po_no, "normal", 16),
            (2, 2, "PO Date:", self.po_date, "normal", 16),
        ]
        for row, col, label, var, state, width in pairs:
            make_label(header, label, width=width).grid(row=row, column=col, sticky="w", pady=5, padx=(0, 4))
            if label == "Bill To:":
                self.customer_combo = ttk.Combobox(header, state="readonly", width=28)
                self.customer_combo.grid(row=row, column=col + 1, sticky="ew", padx=(8, 16), pady=5)
            elif label == "PO Date:":
                po_date_wrap = tk.Frame(header, bg=CARD_BG)
                po_date_wrap.grid(row=row, column=col + 1, sticky="ew", padx=(8, 16), pady=5)
                po_date_wrap.grid_columnconfigure(0, weight=1)
                ttk.Entry(po_date_wrap, textvariable=var, width=16, state=state).grid(row=0, column=0, sticky="ew")
                ttk.Button(po_date_wrap, text="Pick", width=6, command=self.open_po_date_picker).grid(row=0, column=1, padx=(6, 0))
            else:
                ttk.Entry(header, textvariable=var, width=20, state=state).grid(row=row, column=col + 1, sticky="ew", padx=(8, 16), pady=5)
        self.customer_combo.bind("<<ComboboxSelected>>", self.select_customer)

    def open_po_date_picker(self) -> None:
        picker = DatePickerPopup(self, self.po_date, self.po_date.get())
        picker.update_idletasks()
        x = self.winfo_rootx() + 180
        y = self.winfo_rooty() + 120
        picker.geometry(f"+{x}+{y}")

    def _build_body(self) -> None:
        split = tk.Frame(self.body, bg=CARD_BG)
        split.pack(fill="both", expand=True, pady=(12, 0))
        left = tk.Frame(split, bg=CARD_BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = tk.Frame(split, bg=CARD_BG)
        right.pack(side="left", fill="both", expand=True)

        search_row = tk.Frame(left, bg=CARD_BG)
        search_row.pack(fill="x")
        make_label(search_row, "Search:", width=8).pack(side="left")
        search = ttk.Entry(search_row, textvariable=self.search_item, width=24)
        search.pack(side="left", padx=8)
        search.bind("<KeyRelease>", lambda _e: self.load_items())

        cols = ("id", "name", "make", "rate", "ratio", "stock", "unit")
        self.item_tree = ttk.Treeview(left, columns=cols, show="headings", height=12)
        for col, width in zip(cols, [55, 125, 110, 75, 75, 75, 70]):
            self.item_tree.heading(col, text=col.title())
            self.item_tree.column(col, width=width, anchor="center")
        self.item_tree.pack(fill="both", expand=True, pady=8)
        self.item_tree.bind("<<TreeviewSelect>>", self.select_item)

        detail = tk.Frame(left, bg=CARD_BG)
        detail.pack(fill="x")
        fields = [
            ("P No:", "item_id"),
            ("Product:", "item_name"),
            ("Make:", "make"),
            ("Sr No:", "serial"),
            ("Unit:", "unit"),
            ("Ratio:", "ratio"),
            ("Stock:", "stock"),
            ("Unit Price:", "unit_price"),
            ("Quantity:", "quantity"),
            ("Total:", "line_total"),
        ]
        for idx, (label, key) in enumerate(fields):
            r = idx // 3
            c = (idx % 3) * 2
            make_label(detail, label, width=10, bg=CARD_BG).grid(row=r, column=c, sticky="w", pady=5)
            entry = ttk.Entry(detail, textvariable=self.item_vars[key], width=16)
            entry.grid(row=r, column=c + 1, sticky="w", padx=(6, 16), pady=5)
            if key in {"item_id", "item_name", "make", "unit", "ratio", "stock", "line_total"}:
                entry.configure(state="readonly")
            if key == "quantity":
                entry.bind("<KeyRelease>", lambda _e: self.calculate_total())
        add_row = tk.Frame(left, bg=CARD_BG)
        add_row.pack(fill="x", pady=(10, 0))
        add_row.grid_columnconfigure(0, weight=1)
        ttk.Button(add_row, text="ADD", command=self.add_item, style="Primary.TButton").grid(row=0, column=0, sticky="ew", padx=60)

        cart_cols = ("item_id", "item_name", "make", "serial", "unit_price", "qty", "total")
        self.cart_tree = ttk.Treeview(right, columns=cart_cols, show="headings", height=15)
        for col, width in zip(cart_cols, [60, 140, 110, 100, 85, 70, 85]):
            self.cart_tree.heading(col, text=col.replace("_", " ").title())
            self.cart_tree.column(col, width=width, anchor="center")
        self.cart_tree.pack(fill="both", expand=True, pady=(0, 8))

        remove_row = tk.Frame(right, bg=CARD_BG)
        remove_row.pack(fill="x", pady=(0, 10))
        remove_row.grid_columnconfigure(0, weight=1)
        ttk.Button(remove_row, text="REMOVE", command=self.remove_selected, style="Neutral.TButton").grid(row=0, column=0, sticky="ew", padx=80)

        totals = tk.Frame(right, bg=CARD_BG)
        totals.pack(fill="x")
        for idx, (label, var, state) in enumerate([
            ("Sub Total:", self.subtotal, "readonly"),
            ("Tax (%):", self.tax_percent, "normal"),
            ("Tax Amt:", self.tax_amount, "readonly"),
            ("Total:", self.total, "readonly"),
        ]):
            make_label(totals, label, width=10).grid(row=0, column=idx * 2, sticky="w", pady=5)
            entry = ttk.Entry(totals, textvariable=var, width=10, state=state)
            entry.grid(row=0, column=idx * 2 + 1, padx=(6, 14), pady=5)
            if label == "Tax (%):":
                entry.bind("<KeyRelease>", lambda _e: self.recalculate_totals())

        buttons = tk.Frame(right, bg=CARD_BG)
        buttons.pack(fill="x", pady=(12, 0))
        actions = [
            ("PRINT", self.export_current),
            ("SAVE", self.save_bill),
            ("NEW", self.reset_bill),
            ("EXIT", self.destroy),
        ]
        for index, (text, command) in enumerate(actions):
            buttons.grid_columnconfigure(index, weight=1)
            style_name = "Primary.TButton" if text == "SAVE" else "Neutral.TButton"
            ttk.Button(buttons, text=text, command=command, style=style_name).grid(row=0, column=index, padx=8, sticky="ew")

    def refresh(self) -> None:
        self.bill_no.set(str(self.db.next_bill_number()))
        customers = self.db.list_customers()
        self.customer_map = {row["name"]: row["id"] for row in customers}
        self.customer_combo["values"] = list(self.customer_map.keys())
        self.load_items()
        self.recalculate_totals()

    def load_items(self) -> None:
        for iid in self.item_tree.get_children():
            self.item_tree.delete(iid)
        search = self.search_item.get().strip().lower()
        for row in self.db.list_items():
            if search and search not in row["name"].lower():
                continue
            self.item_tree.insert("", "end", values=(row["id"], row["name"], row["make_name"], f"{row['rate']:.2f}", f"{row['ratio']:.2f}", format_stock(row["stock"]), row["unit"]))

    def select_customer(self, _event=None) -> None:
        customer_id = self.customer_map.get(self.customer_combo.get())
        if not customer_id:
            return
        customer = self.db.get_customer(customer_id)
        if not customer:
            return
        self.customer_id.set(str(customer["id"]))
        self.cst_no.set(customer["cst_no"])
        self.tin_no.set(customer["tin_no"])

    def select_item(self, _event=None) -> None:
        if not self.item_tree.selection():
            return
        values = self.item_tree.item(self.item_tree.selection()[0], "values")
        self.selected_item_id = int(values[0])
        self.item_vars["item_id"].set(values[0])
        self.item_vars["item_name"].set(values[1])
        self.item_vars["make"].set(values[2])
        self.item_vars["unit_price"].set(values[3])
        self.item_vars["ratio"].set(values[4])
        self.item_vars["stock"].set(values[5])
        self.item_vars["unit"].set(values[6])
        self.item_vars["serial"].set("")
        self.item_vars["quantity"].set("")
        self.item_vars["line_total"].set("0.00")

    def calculate_total(self) -> None:
        try:
            price = float(self.item_vars["unit_price"].get())
            qty = float(self.item_vars["quantity"].get())
            self.item_vars["line_total"].set(f"{price * qty:.2f}")
        except ValueError:
            self.item_vars["line_total"].set("0.00")

    def add_item(self) -> None:
        try:
            item_id = int(self.item_vars["item_id"].get())
            unit_price = float(self.item_vars["unit_price"].get())
            quantity = float(self.item_vars["quantity"].get())
        except ValueError:
            messagebox.showerror("Validation Error", "Select an item and enter a valid quantity.", parent=self)
            return
        if quantity <= 0:
            messagebox.showerror("Validation Error", "Quantity must be greater than zero.", parent=self)
            return
        available_stock = float(self.item_vars["stock"].get() or 0)
        quantity_in_cart = sum(item["quantity"] for item in self.current_cart if int(item["item_id"]) == item_id)
        remaining_stock = available_stock - quantity_in_cart
        if quantity > remaining_stock:
            messagebox.showerror(
                "Stock Alert",
                f"Only {format_stock(remaining_stock)} units are available for this item.",
                parent=self,
            )
            return
        line = {
            "item_id": item_id,
            "item_name": self.item_vars["item_name"].get(),
            "item_make": self.item_vars["make"].get(),
            "serial_no": self.item_vars["serial"].get(),
            "unit_price": unit_price,
            "quantity": quantity,
            "total": unit_price * quantity,
        }
        self.current_cart.append(line)
        self.cart_tree.insert("", "end", values=(line["item_id"], line["item_name"], line["item_make"], line["serial_no"], f"{unit_price:.2f}", f"{quantity:.2f}", f"{line['total']:.2f}"))
        for key in self.item_vars:
            self.item_vars[key].set("")
        self.recalculate_totals()

    def remove_selected(self) -> None:
        if not self.cart_tree.selection():
            return
        index = self.cart_tree.index(self.cart_tree.selection()[0])
        del self.current_cart[index]
        self.cart_tree.delete(self.cart_tree.selection()[0])
        self.recalculate_totals()

    def recalculate_totals(self) -> None:
        subtotal = sum(item["total"] for item in self.current_cart)
        try:
            tax_percent = float(self.tax_percent.get() or 0)
        except ValueError:
            tax_percent = 0.0
        tax_amount = subtotal * tax_percent / 100
        total = subtotal + tax_amount
        self.subtotal.set(f"{subtotal:.2f}")
        self.tax_amount.set(f"{tax_amount:.2f}")
        self.total.set(f"{total:.2f}")

    def validate_bill(self) -> bool:
        if not self.customer_id.get():
            messagebox.showerror("Validation Error", "Please select a customer.", parent=self)
            return False
        if not self.current_cart:
            messagebox.showerror("Validation Error", "No items added to the bill.", parent=self)
            return False
        try:
            dt.date.fromisoformat(self.bill_date.get())
        except ValueError:
            messagebox.showerror("Validation Error", "Bill date must be YYYY-MM-DD.", parent=self)
            return False
        if self.po_date.get().strip():
            try:
                dt.date.fromisoformat(self.po_date.get())
            except ValueError:
                messagebox.showerror("Validation Error", "PO date must be YYYY-MM-DD.", parent=self)
                return False
        try:
            if float(self.tax_percent.get() or 0) < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Validation Error", "Tax rate must be a valid positive number.", parent=self)
            return False
        return True

    def save_bill(self) -> None:
        if not self.validate_bill():
            return
        header = {
            "bill_date": self.bill_date.get(),
            "customer_id": int(self.customer_id.get()),
            "customer_name": self.customer_combo.get(),
            "po_no": self.po_no.get().strip(),
            "po_date": self.po_date.get().strip(),
            "cst_no": self.cst_no.get().strip(),
            "tin_no": self.tin_no.get().strip(),
            "subtotal": float(self.subtotal.get()),
            "tax_percent": float(self.tax_percent.get() or 0),
            "tax_amount": float(self.tax_amount.get()),
            "total": float(self.total.get()),
        }
        try:
            bill_id = self.db.save_bill(header, self.current_cart)
        except ValueError as exc:
            messagebox.showerror("Stock Alert", str(exc), parent=self)
            return
        messagebox.showinfo("Saved", f"Bill #{bill_id} saved successfully.", parent=self)
        self.on_change()
        self.reset_bill()

    def export_current(self) -> None:
        if not self.validate_bill():
            return
        bill = {
            "id": int(self.bill_no.get()),
            "bill_date": self.bill_date.get(),
            "customer_name": self.customer_combo.get(),
            "po_no": self.po_no.get().strip(),
            "po_date": self.po_date.get().strip(),
            "cst_no": self.cst_no.get().strip(),
            "tin_no": self.tin_no.get().strip(),
            "subtotal": float(self.subtotal.get()),
            "tax_percent": float(self.tax_percent.get() or 0),
            "tax_amount": float(self.tax_amount.get()),
            "total": float(self.total.get()),
        }
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save Bill PDF",
            defaultextension=".pdf",
            initialdir=str(APP_DIR / "exports"),
            initialfile=f"Bill_{self.bill_no.get()}.pdf",
            filetypes=[("PDF Files", "*.pdf")],
        )
        if not path:
            return
        try:
            export_bill_pdf(bill, self.current_cart, path)
        except Exception as exc:
            messagebox.showerror("PDF Export Failed", f"Could not generate the bill PDF.\n{exc}", parent=self)
            return
        messagebox.showinfo("Saved", f"Saved bill to:\n{path}", parent=self)

    def reset_bill(self) -> None:
        self.current_cart.clear()
        for iid in self.cart_tree.get_children():
            self.cart_tree.delete(iid)
        for key in self.item_vars:
            self.item_vars[key].set("")
        self.bill_no.set(str(self.db.next_bill_number()))
        self.bill_date.set(dt.date.today().isoformat())
        self.customer_id.set("")
        self.cst_no.set("")
        self.tin_no.set("")
        self.po_no.set("")
        self.po_date.set("")
        self.tax_percent.set("0")
        self.customer_combo.set("")
        self.load_items()
        self.recalculate_totals()


class BillsWindow(BaseChildWindow):
    def __init__(self, master, db: DatabaseManager) -> None:
        super().__init__(master, "BILL INFORMATION", 1080, 670)
        self.db = db
        self.bill_search = tk.StringVar()
        self.customer_search = tk.StringVar()
        self.selected_bill_id: int | None = None
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        search1 = tk.Frame(self.body, bg=CARD_BG)
        search1.pack(fill="x", pady=(0, 8))
        make_label(search1, "Search by Bill No:", width=18).pack(side="left")
        bill_entry = ttk.Entry(search1, textvariable=self.bill_search, width=18)
        bill_entry.pack(side="left", padx=8)
        bill_entry.bind("<KeyRelease>", lambda _e: self.refresh())

        search2 = tk.Frame(self.body, bg=CARD_BG)
        search2.pack(fill="x", pady=(0, 8))
        make_label(search2, "Search by Customer Name:", width=24).pack(side="left")
        customer_entry = ttk.Entry(search2, textvariable=self.customer_search, width=24)
        customer_entry.pack(side="left", padx=8)
        customer_entry.bind("<KeyRelease>", lambda _e: self.refresh())

        cols = ("id", "bill_date", "customer_name", "subtotal", "tax_amount", "total")
        self.tree = ttk.Treeview(self.body, columns=cols, show="headings", height=14)
        for col, width in zip(cols, [80, 120, 220, 110, 110, 110]):
            self.tree.heading(col, text=col.replace("_", " ").title())
            self.tree.column(col, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True, pady=(6, 10))
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        self.items_tree = ttk.Treeview(self.body, columns=("item_id", "item_name", "item_make", "serial_no", "unit_price", "quantity", "total"), show="headings", height=8)
        for col, width in zip(("item_id", "item_name", "item_make", "serial_no", "unit_price", "quantity", "total"), [70, 180, 120, 110, 100, 90, 100]):
            self.items_tree.heading(col, text=col.replace("_", " ").title())
            self.items_tree.column(col, width=width, anchor="center")
        self.items_tree.pack(fill="both", expand=True, pady=(0, 10))

        self.add_button_bar(self.body, [("REFRESH", self.refresh), ("PRINT", self.export_selected), ("EXIT", self.destroy)])

    def refresh(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for iid in self.items_tree.get_children():
            self.items_tree.delete(iid)
        self.selected_bill_id = None
        for row in self.db.list_bills(self.bill_search.get(), self.customer_search.get()):
            self.tree.insert("", "end", values=(row["id"], row["bill_date"], row["customer_name"], f"{row['subtotal']:.2f}", f"{row['tax_amount']:.2f}", f"{row['total']:.2f}"))

    def on_select(self, _event=None) -> None:
        if not self.tree.selection():
            return
        self.selected_bill_id = int(self.tree.item(self.tree.selection()[0], "values")[0])
        bill, items = self.db.get_bill(self.selected_bill_id)
        for iid in self.items_tree.get_children():
            self.items_tree.delete(iid)
        if not bill:
            return
        for item in items:
            self.items_tree.insert("", "end", values=(item["item_id"], item["item_name"], item["item_make"], item["serial_no"], f"{item['unit_price']:.2f}", f"{item['quantity']:.2f}", f"{item['total']:.2f}"))

    def export_selected(self) -> None:
        if not self.selected_bill_id:
            messagebox.showerror("Print", "Select a bill first.", parent=self)
            return
        bill, items = self.db.get_bill(self.selected_bill_id)
        if not bill:
            return
        path = filedialog.asksaveasfilename(parent=self, title="Save Bill PDF", defaultextension=".pdf", initialdir=str(APP_DIR / "exports"), initialfile=f"Bill_{self.selected_bill_id}.pdf", filetypes=[("PDF Files", "*.pdf")])
        if not path:
            return
        try:
            export_bill_pdf(bill, items, path)
        except Exception as exc:
            messagebox.showerror("PDF Export Failed", f"Could not generate the bill PDF.\n{exc}", parent=self)
            return
        messagebox.showinfo("Saved", f"Saved bill to:\n{path}", parent=self)


class SettingsWindow(BaseChildWindow):
    def __init__(self, master: MainShell, db: DatabaseManager, username: str) -> None:
        super().__init__(master, "CHANGE USERNAME / PASSWORD", 720, 420)
        self.shell = master
        self.db = db
        self.current_username = tk.StringVar(value=username)
        self.new_username = tk.StringVar(value=username)
        self.current_password = tk.StringVar()
        self.new_password = tk.StringVar()
        self.confirm_password = tk.StringVar()

        form = tk.Frame(self.body, bg=CARD_BG)
        form.pack(fill="both", expand=True)
        form.grid_columnconfigure(1, weight=1)
        rows = [
            ("Current Username:", self.current_username, ""),
            ("New Username:", self.new_username, ""),
            ("Current Password:", self.current_password, "*"),
            ("New Password:", self.new_password, "*"),
            ("Confirm Password:", self.confirm_password, "*"),
        ]
        for idx, (label, var, show) in enumerate(rows):
            make_label(form, label, width=18).grid(row=idx, column=0, sticky="w", pady=10)
            ttk.Entry(form, textvariable=var, width=28, show=show).grid(row=idx, column=1, padx=(10, 0), pady=10, sticky="ew")

        buttons = tk.Frame(form, bg=CARD_BG)
        buttons.grid(row=len(rows), column=0, columnspan=2, sticky="ew", pady=(18, 0))
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)
        ttk.Button(buttons, text="SAVE", command=self.update).grid(row=0, column=0, padx=8, sticky="ew")
        ttk.Button(buttons, text="EXIT", command=self.destroy).grid(row=0, column=1, padx=8, sticky="ew")

    def update(self) -> None:
        new_username = self.new_username.get().strip()
        if not new_username:
            messagebox.showerror("Validation", "Username cannot be empty.", parent=self)
            return
        if self.new_password.get() != self.confirm_password.get():
            messagebox.showerror("Mismatch", "New password and confirmation do not match.", parent=self)
            return
        if len(self.new_password.get()) < 4:
            messagebox.showerror("Validation", "Password must be at least 4 characters.", parent=self)
            return
        try:
            self.db.change_credentials(
                self.current_username.get().strip(),
                new_username,
                self.current_password.get(),
                self.new_password.get(),
            )
        except ValueError as exc:
            messagebox.showerror("Update Failed", str(exc), parent=self)
            return
        self.shell.username = new_username
        self.shell.master.current_user = new_username
        self.shell._render()
        messagebox.showinfo("Updated", "Credentials updated successfully.", parent=self)
        self.destroy()


class AboutWindow(BaseChildWindow):
    def __init__(self, master) -> None:
        super().__init__(master, "ABOUT", 620, 420)
        label = tk.Label(
            self.body,
            text="Inventory and Billing System\nPython Tkinter Edition\nStyled to match the original Java Swing project",
            bg=CARD_BG,
            fg=TITLE_FG,
            font=("Helvetica", 16, "bold"),
            justify="center",
        )
        label.pack(pady=(10, 18))

        credits_frame = tk.Frame(self.body, bg=CARD_BG)
        credits_frame.pack(fill="x", expand=True, padx=12)

        tk.Label(
            credits_frame,
            text="Project Credits",
            bg=CARD_BG,
            fg=LABEL_FG,
            font=("Helvetica", 14, "bold"),
            anchor="center",
        ).pack(fill="x", pady=(0, 12))

        credits = [
            "Harshali Shewale - Lead Developer",
            "Payal Deore - UI Designer",
            "Pornima Rane - Backend Engineer",
            "Akanksha Deore - QA Specialist",
        ]
        for credit in credits:
            tk.Label(
                credits_frame,
                text=credit,
                bg=CARD_BG,
                fg=LABEL_FG,
                font=("Helvetica", 12),
                anchor="w",
                justify="left",
            ).pack(fill="x", pady=4)

        self.add_button_bar(self.body, [("OK", self.destroy)])


class AlertsWindow(BaseChildWindow):
    def __init__(self, master, db: DatabaseManager) -> None:
        super().__init__(master, "ALERTS", 860, 520)
        self.db = db
        tk.Label(self.body, text="Items with stock below 100", bg=CARD_BG, fg=TITLE_FG, font=("Helvetica", 15, "bold")).pack(anchor="w", pady=(0, 8))
        cols = ("id", "name", "make", "stock", "rate", "unit")
        tree = ttk.Treeview(self.body, columns=cols, show="headings", height=14)
        for col, width in zip(cols, [70, 200, 150, 90, 100, 100]):
            tree.heading(col, text=col.title())
            tree.column(col, width=width, anchor="center")
        tree.pack(fill="both", expand=True)
        for row in self.db.list_low_stock_items(100):
            tree.insert("", "end", values=(row["id"], row["name"], row["make_name"], format_stock(row["stock"]), f"{row['rate']:.2f}", row["unit"]))
        self.add_button_bar(self.body, [("CLOSE", self.destroy)])


def export_all_customers(db: DatabaseManager) -> None:
    rows = [[str(r["id"]), r["name"], r["phone"], r["email"], r["cst_no"], r["tin_no"]] for r in db.report_customers()]
    path = filedialog.asksaveasfilename(title="Save Customer Report", defaultextension=".pdf", initialdir=str(APP_DIR / "exports"), initialfile="customers_report.pdf", filetypes=[("PDF Files", "*.pdf")])
    if path:
        export_simple_report("Customer Report", ["ID", "Name", "Phone", "Email", "CST", "TIN"], rows, path)
        messagebox.showinfo("Saved", f"Saved report to:\n{path}")


def export_single_customer(db: DatabaseManager) -> None:
    customer_id = simpledialog.askinteger("Single Customer", "Enter Customer ID:")
    if not customer_id:
        return
    customer = db.get_customer(customer_id)
    if not customer:
        messagebox.showerror("Not Found", "Customer not found.")
        return
    path = filedialog.asksaveasfilename(title="Save Single Customer Report", defaultextension=".pdf", initialdir=str(APP_DIR / "exports"), initialfile=f"customer_{customer_id}.pdf", filetypes=[("PDF Files", "*.pdf")])
    if path:
        rows = [[str(customer["id"]), customer["name"], customer["phone"], customer["email"], customer["cst_no"], customer["tin_no"]]]
        export_simple_report("Single Customer Report", ["ID", "Name", "Phone", "Email", "CST", "TIN"], rows, path)
        messagebox.showinfo("Saved", f"Saved report to:\n{path}")


def export_all_items(db: DatabaseManager) -> None:
    rows = [[str(r["id"]), r["name"], r["make_name"], f"{r['rate']:.2f}", f"{r['ratio']:.2f}", r["unit"]] for r in db.report_items()]
    path = filedialog.asksaveasfilename(title="Save Item Report", defaultextension=".pdf", initialdir=str(APP_DIR / "exports"), initialfile="items_report.pdf", filetypes=[("PDF Files", "*.pdf")])
    if path:
        export_simple_report("Item Report", ["ID", "Name", "Make", "Rate", "Ratio", "Unit"], rows, path)
        messagebox.showinfo("Saved", f"Saved report to:\n{path}")


def export_sales(db: DatabaseManager) -> None:
    rows = [[str(r["id"]), r["customer_name"], r["bill_date"], f"{r['subtotal']:.2f}", f"{r['tax_percent']:.2f}", f"{r['tax_amount']:.2f}", f"{r['total']:.2f}"] for r in db.report_sales()]
    path = filedialog.asksaveasfilename(title="Save Sales Report", defaultextension=".pdf", initialdir=str(APP_DIR / "exports"), initialfile="sales_report.pdf", filetypes=[("PDF Files", "*.pdf")])
    if path:
        export_simple_report("Sales Report", ["Bill No", "Customer", "Date", "Subtotal", "Tax %", "Tax Amt", "Total"], rows, path)
        messagebox.showinfo("Saved", f"Saved report to:\n{path}")


def export_selected_bill(db: DatabaseManager) -> None:
    bill_id = simpledialog.askinteger("Bill Report", "Enter Bill Number:")
    if not bill_id:
        return
    bill, items = db.get_bill(bill_id)
    if not bill:
        messagebox.showerror("Not Found", "Bill not found.")
        return
    path = filedialog.asksaveasfilename(title="Save Bill PDF", defaultextension=".pdf", initialdir=str(APP_DIR / "exports"), initialfile=f"Bill_{bill_id}.pdf", filetypes=[("PDF Files", "*.pdf")])
    if path:
        try:
            export_bill_pdf(bill, items, path)
        except Exception as exc:
            messagebox.showerror("PDF Export Failed", f"Could not generate the bill PDF.\n{exc}")
            return
        messagebox.showinfo("Saved", f"Saved bill to:\n{path}")


if __name__ == "__main__":
    app = BillingApp()
    app.mainloop()

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Cal Viewer - ICS Calendar Day Viewer
A simple GTK4 app to view ICS calendar events day by day.
"""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Gio, GLib, Gdk

import sys
import os
import uuid
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import time as _time

def _local_tz() -> ZoneInfo:
    """Return the system local timezone using the TZ env var or /etc/localtime."""
    tz_name = os.environ.get("TZ")
    if not tz_name:
        # Read from timedatectl / symlink
        lt = Path("/etc/localtime")
        if lt.is_symlink():
            target = str(lt.resolve())
            # e.g. /usr/share/zoneinfo/America/Sao_Paulo
            for marker in ("/zoneinfo/", "/zoneinfo\\"):
                idx = target.find(marker)
                if idx != -1:
                    tz_name = target[idx + len(marker):]
                    break
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, KeyError):
            pass
    # Fallback: use UTC offset from time module (no DST name available)
    offset_sec = -_time.timezone if not _time.daylight else -_time.altzone
    from datetime import timezone as _tz
    return _tz(timedelta(seconds=offset_sec))

# ── Config ──────────────────────────────────────────────────────────────────

CONFIG_DIR  = Path(GLib.get_user_config_dir()) / "cal-viewer"
CONFIG_FILE = CONFIG_DIR / "config.json"

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {}

def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

# ── ICS parser (no external deps) ───────────────────────────────────────────

def _unfold(text: str) -> str:
    """Unfold RFC 5545 line continuations."""
    return re.sub(r"\r?\n[ \t]", "", text)

def _parse_dt(value: str, tzid: str | None = None) -> datetime | date | None:
    """Parse a DTSTART/DTEND value into a datetime or date."""
    value = value.strip()
    # Date-only
    if re.fullmatch(r"\d{8}", value):
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    # UTC datetime
    if value.endswith("Z"):
        try:
            dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    # Floating or TZID datetime
    try:
        dt = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        if tzid:
            try:
                tz = ZoneInfo(tzid)
                return dt.replace(tzinfo=tz)
            except (ZoneInfoNotFoundError, KeyError):
                pass
        return dt  # naive / floating
    except ValueError:
        return None

def _parse_rrule(rule_str: str) -> dict:
    """Parse an RRULE string into a dict."""
    result = {}
    for part in rule_str.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.upper()] = v
    return result

def _dt_to_date(dt) -> date | None:
    """Convert datetime or date to date in local time.

    Floating datetimes (no tzinfo) are already in local time — use as-is.
    Aware datetimes (UTC or explicit TZID) are converted to local first.
    """
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            dt = dt.astimezone(_local_tz())
        return dt.date()
    if isinstance(dt, date):
        return dt
    return None

def _event_occurs_on(event: dict, target: date) -> bool:
    """Return True if the event (with possible recurrence) occurs on target date."""
    start_dt = event.get("dtstart")
    end_dt   = event.get("dtend")
    if start_dt is None:
        return False

    start_date = _dt_to_date(start_dt)
    if start_date is None:
        return False

    # Check EXDATE list
    exdates = event.get("exdates", [])
    if target in exdates:
        return False

    rrule = event.get("rrule")

    if not rrule:
        # Single event
        if end_dt:
            end_date = _dt_to_date(end_dt)
            if end_date is None:
                return start_date == target
            # All-day events: DTEND is exclusive
            if isinstance(start_dt, date) and not isinstance(start_dt, datetime):
                return start_date <= target < end_date
            return start_date <= target <= end_date
        return start_date == target

    # Recurring event
    freq     = rrule.get("FREQ", "").upper()
    interval = int(rrule.get("INTERVAL", 1))
    until_s  = rrule.get("UNTIL")
    count_s  = rrule.get("COUNT")
    byday    = rrule.get("BYDAY", "")

    until = None
    if until_s:
        until_dt = _parse_dt(until_s)
        until = _dt_to_date(until_dt) if until_dt else None

    if start_date > target:
        return False
    if until and target > until:
        return False

    # Generate occurrences up to target
    weekday_map = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}

    if freq == "DAILY":
        delta = (target - start_date).days
        return delta % interval == 0

    if freq == "WEEKLY":
        if byday:
            days = [weekday_map[d.strip()[-2:].upper()] for d in byday.split(",") if d.strip()[-2:].upper() in weekday_map]
        else:
            days = [start_date.weekday()]

        weeks_delta = (target - start_date).days // 7
        if weeks_delta % interval != 0 and not (weeks_delta % interval == 0):
            # Check: same week slot
            week_start = start_date + timedelta(weeks=(weeks_delta // interval) * interval)
            pass

        # Simpler: check day-of-week is in list AND week offset matches
        if target.weekday() not in days:
            return False
        # Find how many complete intervals from start_date's week
        days_since = (target - start_date).days
        if days_since < 0:
            return False
        # The week index of target relative to start
        week_idx = days_since // 7
        return week_idx % interval == 0

    if freq == "MONTHLY":
        if (target.year - start_date.year) * 12 + (target.month - start_date.month) < 0:
            return False
        month_delta = (target.year - start_date.year) * 12 + (target.month - start_date.month)
        if month_delta % interval != 0:
            return False
        if byday:
            # e.g. BYDAY=2MO (second Monday)
            for part in byday.split(","):
                part = part.strip()
                m = re.fullmatch(r"([+-]?\d*)([A-Z]{2})", part.upper())
                if m:
                    n_str, wd_str = m.group(1), m.group(2)
                    wd = weekday_map.get(wd_str)
                    if wd is None:
                        continue
                    if target.weekday() != wd:
                        continue
                    if n_str:
                        n = int(n_str)
                        if n > 0:
                            nth = (target.day - 1) // 7 + 1
                            return nth == n
                        else:
                            # negative: count from end
                            import calendar
                            last_day = calendar.monthrange(target.year, target.month)[1]
                            nth_from_end = (last_day - target.day) // 7 + 1
                            return nth_from_end == abs(n)
                    return True
            return False
        return target.day == start_date.day

    if freq == "YEARLY":
        year_delta = target.year - start_date.year
        if year_delta < 0 or year_delta % interval != 0:
            return False
        return target.month == start_date.month and target.day == start_date.day

    return False

def parse_ics(filepath: str) -> list[dict]:
    """Parse an ICS file and return a list of event dicts."""
    try:
        raw = Path(filepath).read_bytes().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"Error reading ICS: {e}", file=sys.stderr)
        return []

    raw = _unfold(raw)
    events = []
    current = None
    in_valarm = False

    for line in raw.splitlines():
        line = line.rstrip("\r")
        if not line:
            continue

        if line.upper() == "BEGIN:VEVENT":
            current = {"exdates": []}
            in_valarm = False
            continue

        if line.upper() == "BEGIN:VALARM":
            in_valarm = True
            continue

        if line.upper() == "END:VALARM":
            in_valarm = False
            continue

        if line.upper() == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            in_valarm = False
            continue

        if current is None or in_valarm:
            continue

        # Split property name and value
        if ":" not in line:
            continue
        prop_full, _, value = line.partition(":")
        prop_full = prop_full.upper()

        # Extract TZID param
        tzid = None
        prop_name = prop_full.split(";")[0]
        for param in prop_full.split(";")[1:]:
            if param.startswith("TZID="):
                tzid = param[5:].strip('"')

        # VALUE=DATE param
        is_date_only = "VALUE=DATE" in prop_full

        if prop_name in ("DTSTART", "DTEND", "DTEND;VALUE=DATE", "DTSTART;VALUE=DATE"):
            prop_key = "dtstart" if "DTSTART" in prop_name else "dtend"
            if is_date_only:
                v = value.strip()
                try:
                    current[prop_key] = date(int(v[:4]), int(v[4:6]), int(v[6:8]))
                except Exception:
                    pass
            else:
                dt = _parse_dt(value, tzid)
                if dt:
                    current[prop_key] = dt

        elif prop_name == "SUMMARY":
            current["summary"] = value.strip()

        elif prop_name == "DESCRIPTION":
            current["description"] = value.replace("\\n", "\n").replace("\\,", ",").strip()

        elif prop_name == "LOCATION":
            current["location"] = value.replace("\\,", ",").strip()

        elif prop_name == "RRULE":
            current["rrule"] = _parse_rrule(value)

        elif prop_name in ("EXDATE", "EXDATE;VALUE=DATE"):
            for v in value.split(","):
                v = v.strip()
                if re.fullmatch(r"\d{8}", v):
                    try:
                        current["exdates"].append(date(int(v[:4]), int(v[4:6]), int(v[6:8])))
                    except Exception:
                        pass
                else:
                    dt = _parse_dt(v, tzid)
                    if dt:
                        d = _dt_to_date(dt)
                        if d:
                            current["exdates"].append(d)

        elif prop_name == "UID":
            current["uid"] = value.strip()

        elif prop_name == "STATUS":
            current["status"] = value.strip().upper()

    return events

def events_for_date(events: list[dict], target: date) -> list[dict]:
    """Filter events that occur on the given date, sorted by start time."""
    result = []
    for ev in events:
        if ev.get("status") == "CANCELLED":
            continue
        if _event_occurs_on(ev, target):
            result.append(ev)

    def sort_key(ev):
        dt = ev.get("dtstart")
        if isinstance(dt, datetime):
            # Convert to local time for sorting
            if dt.tzinfo:
                dt = dt.astimezone(_local_tz())
            return (0, dt.hour * 60 + dt.minute)
        return (1, 0)  # all-day events last... or first

    result.sort(key=sort_key)
    return result

def format_time(dt) -> str:
    """Format a dtstart for display in local time."""
    if isinstance(dt, datetime):
        if dt.tzinfo:
            dt = dt.astimezone(_local_tz())
        return dt.strftime("%H:%M")
    return "Dia todo"

# ── ICS writer ───────────────────────────────────────────────────────────────

def _ics_fold(line: str) -> str:
    """Fold long lines per RFC 5545 (max 75 octets)."""
    result = []
    while len(line.encode("utf-8")) > 75:
        # find safe split point
        n = 75
        while len(line[:n].encode("utf-8")) > 75:
            n -= 1
        result.append(line[:n])
        line = " " + line[n:]
    result.append(line)
    return "\r\n".join(result)

def _dt_to_ics(dt, tzid: str | None = None) -> str:
    """Serialize a datetime/date to ICS property value (with TZID if given)."""
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return f"VALUE=DATE:{dt.strftime('%Y%m%d')}"
    assert isinstance(dt, datetime)
    if tzid:
        return f"TZID={tzid}:{dt.strftime('%Y%m%dT%H%M%S')}"
    if dt.tzinfo is not None:
        dt_utc = dt.astimezone(timezone.utc)
        return f":{dt_utc.strftime('%Y%m%dT%H%M%S')}Z"
    return f":{dt.strftime('%Y%m%dT%H%M%S')}"

def _escape_ics(value: str) -> str:
    """Escape special chars for ICS text properties."""
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

def add_event_to_ics(filepath: str, event: dict) -> bool:
    """Append a new VEVENT to an existing ICS file.
    event dict keys: summary, dtstart (datetime/date), dtend (datetime/date),
                     location (str, optional), description (str, optional),
                     rrule_str (str, optional, raw RRULE value).
    Returns True on success."""
    try:
        raw = Path(filepath).read_bytes().decode("utf-8", errors="replace")
    except Exception:
        return False

    tzid = _local_tz_name()
    uid  = str(uuid.uuid4())
    now  = datetime.now(tz=_local_tz()).strftime("%Y%m%dT%H%M%S")

    lines = []
    lines.append("BEGIN:VEVENT")
    lines.append(f"UID:{uid}")
    lines.append(f"DTSTAMP;TZID={tzid}:{now}")

    dtstart = event["dtstart"]
    dtend   = event["dtend"]
    val_start = _dt_to_ics(dtstart, tzid if isinstance(dtstart, datetime) else None)
    val_end   = _dt_to_ics(dtend,   tzid if isinstance(dtend,   datetime) else None)
    lines.append(_ics_fold(f"DTSTART;{val_start}"))
    lines.append(_ics_fold(f"DTEND;{val_end}"))
    lines.append(_ics_fold(f"SUMMARY:{_escape_ics(event.get('summary', ''))}"))

    loc = event.get("location", "").strip()
    if loc:
        lines.append(_ics_fold(f"LOCATION:{_escape_ics(loc)}"))

    desc = event.get("description", "").strip()
    if desc:
        lines.append(_ics_fold(f"DESCRIPTION:{_escape_ics(desc)}"))

    rrule = event.get("rrule_str", "").strip()
    if rrule:
        lines.append(_ics_fold(f"RRULE:{rrule}"))

    lines.append("END:VEVENT")

    vevent_block = "\r\n".join(lines) + "\r\n"

    # Insert before END:VCALENDAR
    marker = "END:VCALENDAR"
    idx = raw.upper().rfind(marker)
    if idx == -1:
        # No VCALENDAR wrapper — create one
        new_raw = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//cal-viewer//EN\r\n" + vevent_block + "END:VCALENDAR\r\n"
    else:
        new_raw = raw[:idx] + vevent_block + raw[idx:]

    try:
        Path(filepath).write_bytes(new_raw.encode("utf-8"))
        return True
    except Exception:
        return False

def delete_event_from_ics(filepath: str, uid: str, occurrence_date: date | None = None) -> bool:
    """Delete or exclude an event from the ICS file.
    - If occurrence_date is None (non-recurring): remove the VEVENT block entirely.
    - If occurrence_date is given (recurring): add EXDATE to the VEVENT.
    Returns True on success."""
    try:
        raw = Path(filepath).read_bytes().decode("utf-8", errors="replace")
    except Exception:
        return False

    unfolded = _unfold(raw)
    lines_orig = raw.splitlines(keepends=True)

    # Find the VEVENT block boundaries in the unfolded text, then map back to original
    # Strategy: work on unfolded lines to find the block, rewrite raw
    unfolded_lines = unfolded.splitlines(keepends=True)

    # Locate the VEVENT with matching UID in unfolded lines
    block_start = None
    block_end   = None
    for i, line in enumerate(unfolded_lines):
        if line.strip().upper() == "BEGIN:VEVENT":
            block_start = i
        if block_start is not None and ":" in line:
            prop, _, val = line.partition(":")
            if prop.strip().upper() == "UID" and val.strip() == uid:
                # found our block — now find END:VEVENT
                for j in range(block_start, len(unfolded_lines)):
                    if unfolded_lines[j].strip().upper() == "END:VEVENT":
                        block_end = j
                        break
                break
        if line.strip().upper() == "END:VEVENT":
            block_start = None  # reset if no UID match before end

    if block_start is None or block_end is None:
        return False

    block_lines = unfolded_lines[block_start : block_end + 1]

    if occurrence_date is None:
        # Remove the entire block
        new_unfolded_lines = unfolded_lines[:block_start] + unfolded_lines[block_end + 1:]
    else:
        # Add EXDATE for this occurrence
        exdate_val = occurrence_date.strftime("%Y%m%d")
        # Check if EXDATE already exists in block — append to it or add new line
        new_block = []
        exdate_added = False
        for line in block_lines:
            stripped = line.rstrip("\r\n")
            prop = stripped.split(":")[0].split(";")[0].upper()
            if prop == "EXDATE" and not exdate_added:
                # append to existing EXDATE
                stripped = stripped.rstrip() + "," + exdate_val
                new_block.append(stripped + "\r\n")
                exdate_added = True
            elif stripped.upper() == "END:VEVENT":
                if not exdate_added:
                    new_block.append(f"EXDATE;VALUE=DATE:{exdate_val}\r\n")
                new_block.append(line)
            else:
                new_block.append(line)
        new_unfolded_lines = unfolded_lines[:block_start] + new_block + unfolded_lines[block_end + 1:]

    new_raw = "".join(new_unfolded_lines)
    try:
        Path(filepath).write_bytes(new_raw.encode("utf-8"))
        return True
    except Exception:
        return False

def _local_tz_name() -> str:
    """Return the local timezone name string."""
    tz = _local_tz()
    if hasattr(tz, "key"):
        return tz.key
    # fixed-offset fallback
    offset = tz.utcoffset(datetime.now())
    total  = int(offset.total_seconds())
    sign   = "+" if total >= 0 else "-"
    h, m   = divmod(abs(total) // 60, 60)
    return f"UTC{sign}{h:02d}:{m:02d}"

# ── GTK4 Application ─────────────────────────────────────────────────────────

class CalViewerApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.rafaelortiz.cal-viewer",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.cfg      = load_config()
        self.ics_path = self.cfg.get("ics_path", "")
        self.events   = []
        self.current_date = date.today()

        self.connect("activate", self._on_activate)

    # ── Window setup ────────────────────────────────────────────────────────

    def _on_activate(self, app):
        self.win = Adw.ApplicationWindow(application=app)
        self.win.set_title("Cal Viewer")
        self.win.set_default_size(480, 600)

        # ── Header bar ──
        header = Adw.HeaderBar()
        header.add_css_class("flat")

        open_btn = Gtk.Button(icon_name="document-open-symbolic")
        open_btn.set_tooltip_text("Selecionar arquivo ICS")
        open_btn.connect("clicked", self._on_open_ics)
        header.pack_start(open_btn)

        new_btn = Gtk.Button(icon_name="list-add-symbolic")
        new_btn.set_tooltip_text("Novo evento")
        new_btn.connect("clicked", self._on_new_event)
        header.pack_start(new_btn)

        today_btn = Gtk.Button(label="Hoje")
        today_btn.connect("clicked", self._go_today)
        header.pack_end(today_btn)

        # ── Navigation bar ──
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        nav_box.set_margin_start(8)
        nav_box.set_margin_end(8)

        prev_btn = Gtk.Button(icon_name="go-previous-symbolic")
        prev_btn.set_tooltip_text("Dia anterior")
        prev_btn.add_css_class("flat")
        prev_btn.add_css_class("circular")
        prev_btn.connect("clicked", self._go_prev)

        next_btn = Gtk.Button(icon_name="go-next-symbolic")
        next_btn.set_tooltip_text("Próximo dia")
        next_btn.add_css_class("flat")
        next_btn.add_css_class("circular")
        next_btn.connect("clicked", self._go_next)

        # Date button (clicável → abre calendário)
        self.date_btn = Gtk.Button()
        self.date_btn.add_css_class("flat")
        self.date_btn.set_tooltip_text("Selecionar data")
        self.date_btn.set_hexpand(True)

        self.date_label = Gtk.Label()
        self.date_label.add_css_class("heading")
        self.date_btn.set_child(self.date_label)
        self.date_btn.connect("clicked", self._open_calendar_picker)

        # ── Calendar popover ──
        self._cal_popover = Gtk.Popover()
        self._cal_popover.set_parent(self.date_btn)
        self._cal_popover.set_position(Gtk.PositionType.BOTTOM)
        self._cal_popover.set_autohide(True)

        self._gtk_calendar = Gtk.Calendar()
        self._gtk_calendar.set_margin_top(6)
        self._gtk_calendar.set_margin_bottom(6)
        self._gtk_calendar.set_margin_start(6)
        self._gtk_calendar.set_margin_end(6)
        self._gtk_calendar.connect("day-selected", self._on_calendar_day_selected)
        self._cal_popover.set_child(self._gtk_calendar)

        nav_box.append(prev_btn)
        nav_box.append(self.date_btn)
        nav_box.append(next_btn)

        # ── Event list ──
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_vexpand(True)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list")
        self.list_box.set_margin_start(12)
        self.list_box.set_margin_end(12)
        self.list_box.set_margin_top(6)
        self.list_box.set_margin_bottom(12)

        self.scroll.set_child(self.list_box)

        # ── Status / empty page ──
        self.status_page = Adw.StatusPage()
        self.status_page.set_icon_name("x-office-calendar-symbolic")
        self.status_page.set_vexpand(True)

        # ── Main layout ──
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(header)
        main_box.append(nav_box)
        main_box.set_spacing(6)

        self.content_stack = Gtk.Stack()
        self.content_stack.add_named(self.scroll,       "list")
        self.content_stack.add_named(self.status_page,  "status")

        main_box.append(self.content_stack)

        self.win.set_content(main_box)

        # Keyboard navigation
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key)
        self.win.add_controller(key_ctrl)

        # Load ICS if saved
        if self.ics_path and Path(self.ics_path).exists():
            self._load_ics(self.ics_path)
        else:
            self._show_status(
                "Nenhum arquivo ICS selecionado",
                "Clique no botão abrir (pasta) para selecionar um arquivo .ics",
                "document-open-symbolic",
            )

        self._refresh()
        self.win.present()

    # ── ICS loading ─────────────────────────────────────────────────────────

    def _load_ics(self, path: str):
        self.ics_path = path
        self.cfg["ics_path"] = path
        save_config(self.cfg)
        self.events = parse_ics(path)
        self._refresh()

    def _on_open_ics(self, _btn):
        dialog = Gtk.FileDialog()
        dialog.set_title("Selecionar arquivo ICS")

        ics_filter = Gtk.FileFilter()
        ics_filter.set_name("Arquivos de calendário (*.ics)")
        ics_filter.add_pattern("*.ics")
        ics_filter.add_mime_type("text/calendar")

        all_filter = Gtk.FileFilter()
        all_filter.set_name("Todos os arquivos")
        all_filter.add_pattern("*")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(ics_filter)
        filters.append(all_filter)
        dialog.set_filters(filters)
        dialog.set_default_filter(ics_filter)

        # Start in last-known directory or home
        start_path = self.ics_path or str(Path.home())
        if Path(start_path).is_file():
            start_path = str(Path(start_path).parent)
        if Path(start_path).is_dir():
            dialog.set_initial_folder(Gio.File.new_for_path(start_path))

        dialog.open(self.win, None, self._on_file_chosen)

    def _on_file_chosen(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
            if gfile:
                self._load_ics(gfile.get_path())
        except GLib.Error:
            pass

    # ── Navigation ──────────────────────────────────────────────────────────

    def _go_prev(self, _btn=None):
        self.current_date -= timedelta(days=1)
        self._refresh()

    def _go_next(self, _btn=None):
        self.current_date += timedelta(days=1)
        self._refresh()

    def _go_today(self, _btn=None):
        self.current_date = date.today()
        self._refresh()

    def _open_calendar_picker(self, _btn=None):
        d = self.current_date
        # GLib months: 0-based; Gtk.Calendar uses year/month/day properties
        self._gtk_calendar.select_day(
            GLib.DateTime.new_local(d.year, d.month, d.day, 0, 0, 0)
        )
        self._cal_popover.popup()

    def _on_calendar_day_selected(self, cal):
        gdt = cal.get_date()
        self.current_date = date(gdt.get_year(), gdt.get_month(), gdt.get_day_of_month())
        self._cal_popover.popdown()
        self._refresh()

    def _on_key(self, _ctrl, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Left:
            self._go_prev()
            return True
        if keyval == Gdk.KEY_Right:
            self._go_next()
            return True
        if keyval == Gdk.KEY_Home:
            self._go_today()
            return True
        return False

    # ── Rendering ───────────────────────────────────────────────────────────

    def _refresh(self):
        d = self.current_date

        # Date label
        weekdays_pt = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        months_pt   = [
            "janeiro","fevereiro","março","abril","maio","junho",
            "julho","agosto","setembro","outubro","novembro","dezembro",
        ]
        wd  = weekdays_pt[d.weekday()]
        mon = months_pt[d.month - 1]
        label = f"{wd}, {d.day} de {mon} de {d.year}"

        self.date_label.set_label(label)
        self.win.set_title(f"Cal Viewer — {d.strftime('%d/%m/%Y')}")

        # Clear list
        while True:
            child = self.list_box.get_first_child()
            if child is None:
                break
            self.list_box.remove(child)

        if not self.ics_path or not Path(self.ics_path).exists():
            self._show_status(
                "Nenhum arquivo ICS selecionado",
                "Clique no botão abrir (pasta) para selecionar um arquivo .ics",
                "document-open-symbolic",
            )
            return

        evs = events_for_date(self.events, d)

        if not evs:
            self._show_status(
                "Nenhum compromisso",
                f"Sem eventos para {d.strftime('%d/%m/%Y')}",
                "emblem-ok-symbolic",
            )
            return

        self.content_stack.set_visible_child_name("list")

        for ev in evs:
            row = self._build_event_row(ev)
            self.list_box.append(row)

    def _build_event_row(self, ev: dict) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_activatable(False)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hbox.set_margin_start(12)
        hbox.set_margin_end(12)
        hbox.set_margin_top(10)
        hbox.set_margin_bottom(10)

        # Time badge
        time_str = format_time(ev.get("dtstart"))
        time_lbl = Gtk.Label(label=time_str)
        time_lbl.set_width_chars(7)
        time_lbl.set_xalign(1.0)
        time_lbl.add_css_class("dim-label")
        time_lbl.add_css_class("caption")
        hbox.append(time_lbl)

        # Separator dot
        sep = Gtk.Label(label="·")
        sep.add_css_class("dim-label")
        hbox.append(sep)

        # Text info
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_hexpand(True)

        summary = ev.get("summary", "(sem título)")
        title_lbl = Gtk.Label(label=summary)
        title_lbl.set_xalign(0.0)
        title_lbl.set_wrap(True)
        title_lbl.set_wrap_mode(2)  # WORD_CHAR
        title_lbl.add_css_class("body")
        vbox.append(title_lbl)

        location = ev.get("location", "").strip()
        if location:
            loc_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            loc_icon = Gtk.Image.new_from_icon_name("mark-location-symbolic")
            loc_icon.set_pixel_size(12)
            loc_icon.add_css_class("dim-label")
            loc_lbl = Gtk.Label(label=location)
            loc_lbl.set_xalign(0.0)
            loc_lbl.set_ellipsize(3)  # END
            loc_lbl.add_css_class("caption")
            loc_lbl.add_css_class("dim-label")
            loc_box.append(loc_icon)
            loc_box.append(loc_lbl)
            vbox.append(loc_box)

        desc = ev.get("description", "").strip()
        if desc:
            # Show first line only
            first_line = desc.splitlines()[0][:100]
            if len(first_line) == 100:
                first_line += "…"
            desc_lbl = Gtk.Label(label=first_line)
            desc_lbl.set_xalign(0.0)
            desc_lbl.set_ellipsize(3)
            desc_lbl.add_css_class("caption")
            desc_lbl.add_css_class("dim-label")
            vbox.append(desc_lbl)

        hbox.append(vbox)

        # End time (if has dtend and is timed)
        dtstart = ev.get("dtstart")
        dtend   = ev.get("dtend")
        if isinstance(dtstart, datetime) and isinstance(dtend, datetime):
            end_str = format_time(dtend)
            end_lbl = Gtk.Label(label=end_str)
            end_lbl.add_css_class("dim-label")
            end_lbl.add_css_class("caption")
            hbox.append(end_lbl)

        # Delete button
        del_btn = Gtk.Button(icon_name="user-trash-symbolic")
        del_btn.set_tooltip_text("Deletar evento")
        del_btn.add_css_class("flat")
        del_btn.add_css_class("circular")
        del_btn.set_valign(Gtk.Align.CENTER)
        del_btn.connect("clicked", lambda _, e=ev: self._on_delete_event(e))
        hbox.append(del_btn)

        row.set_child(hbox)
        return row

    def _show_status(self, title: str, desc: str, icon: str):
        self.status_page.set_title(title)
        self.status_page.set_description(desc)
        self.status_page.set_icon_name(icon)
        self.content_stack.set_visible_child_name("status")

    # ── New event dialog ─────────────────────────────────────────────────────

    def _on_new_event(self, _btn=None):
        if not self.ics_path:
            self._show_no_ics_toast()
            return
        self._open_event_dialog()

    def _show_no_ics_toast(self):
        toast = Adw.Toast(title="Selecione um arquivo ICS primeiro")
        toast.set_timeout(3)
        # wrap win content in overlay if not already
        content = self.win.get_content()
        if isinstance(content, Adw.ToastOverlay):
            content.add_toast(toast)
        else:
            overlay = Adw.ToastOverlay()
            self.win.set_content(overlay)
            overlay.set_child(content)
            overlay.add_toast(toast)

    def _open_event_dialog(self, _btn=None):
        d = self.current_date

        dialog = Adw.Dialog()
        dialog.set_title("Novo Evento")
        dialog.set_content_width(420)

        # ── Toolbar + header ──
        toolbar_view = Adw.ToolbarView()
        dlg_header = Adw.HeaderBar()
        dlg_header.add_css_class("flat")

        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.connect("clicked", lambda _: dialog.close())
        dlg_header.pack_start(cancel_btn)

        save_btn = Gtk.Button(label="Salvar")
        save_btn.add_css_class("suggested-action")
        dlg_header.pack_end(save_btn)

        toolbar_view.add_top_bar(dlg_header)

        # ── Form ──
        prefs = Adw.PreferencesGroup()
        prefs.set_margin_top(12)
        prefs.set_margin_bottom(12)
        prefs.set_margin_start(12)
        prefs.set_margin_end(12)

        # Summary
        summary_row = Adw.EntryRow()
        summary_row.set_title("Título")
        prefs.add(summary_row)

        # Location
        location_row = Adw.EntryRow()
        location_row.set_title("Local")
        prefs.add(location_row)

        # All-day toggle
        allday_row = Adw.SwitchRow()
        allday_row.set_title("Dia todo")
        prefs.add(allday_row)

        # Date
        date_row = Adw.ActionRow()
        date_row.set_title("Data")
        date_entry = Gtk.Entry()
        date_entry.set_text(d.strftime("%d/%m/%Y"))
        date_entry.set_width_chars(12)
        date_entry.set_valign(Gtk.Align.CENTER)
        date_row.add_suffix(date_entry)
        prefs.add(date_row)

        # Start time
        start_row = Adw.ActionRow()
        start_row.set_title("Início")
        start_entry = Gtk.Entry()
        start_entry.set_text("09:00")
        start_entry.set_width_chars(6)
        start_entry.set_valign(Gtk.Align.CENTER)
        start_row.add_suffix(start_entry)
        prefs.add(start_row)

        # End time
        end_row = Adw.ActionRow()
        end_row.set_title("Fim")
        end_entry = Gtk.Entry()
        end_entry.set_text("10:00")
        end_entry.set_width_chars(6)
        end_entry.set_valign(Gtk.Align.CENTER)
        end_row.add_suffix(end_entry)
        prefs.add(end_row)

        # Recurrence
        rrule_row = Adw.ComboRow()
        rrule_row.set_title("Repetição")
        rrule_model = Gtk.StringList.new([
            "Nunca", "Diariamente", "Semanalmente",
            "Mensalmente", "Anualmente",
        ])
        rrule_row.set_model(rrule_model)
        prefs.add(rrule_row)

        # Description
        desc_row = Adw.EntryRow()
        desc_row.set_title("Descrição")
        prefs.add(desc_row)

        # Toggle time rows visibility
        def on_allday_toggle(row, _param):
            is_allday = row.get_active()
            start_row.set_visible(not is_allday)
            end_row.set_visible(not is_allday)
        allday_row.connect("notify::active", on_allday_toggle)

        # Error label
        error_lbl = Gtk.Label()
        error_lbl.add_css_class("error")
        error_lbl.set_margin_bottom(8)
        error_lbl.set_visible(False)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_box.append(prefs)
        content_box.append(error_lbl)
        toolbar_view.set_content(content_box)
        dialog.set_child(toolbar_view)

        def on_save(_btn):
            # Validate & parse
            summary = summary_row.get_text().strip()
            if not summary:
                error_lbl.set_label("O título é obrigatório.")
                error_lbl.set_visible(True)
                return

            date_txt = date_entry.get_text().strip()
            try:
                ev_date = datetime.strptime(date_txt, "%d/%m/%Y").date()
            except ValueError:
                error_lbl.set_label("Data inválida. Use DD/MM/AAAA.")
                error_lbl.set_visible(True)
                return

            is_allday = allday_row.get_active()

            if is_allday:
                dtstart = ev_date
                dtend   = ev_date + timedelta(days=1)
            else:
                try:
                    sh, sm = [int(x) for x in start_entry.get_text().strip().split(":")]
                    eh, em = [int(x) for x in end_entry.get_text().strip().split(":")]
                except Exception:
                    error_lbl.set_label("Hora inválida. Use HH:MM.")
                    error_lbl.set_visible(True)
                    return
                tz = _local_tz()
                dtstart = datetime(ev_date.year, ev_date.month, ev_date.day, sh, sm, tzinfo=tz)
                dtend   = datetime(ev_date.year, ev_date.month, ev_date.day, eh, em, tzinfo=tz)
                if dtend <= dtstart:
                    dtend += timedelta(days=1)

            rrule_map = {
                1: "FREQ=DAILY",
                2: "FREQ=WEEKLY",
                3: "FREQ=MONTHLY",
                4: "FREQ=YEARLY",
            }
            rrule_str = rrule_map.get(rrule_row.get_selected(), "")

            ev = {
                "summary":     summary,
                "dtstart":     dtstart,
                "dtend":       dtend,
                "location":    location_row.get_text().strip(),
                "description": desc_row.get_text().strip(),
                "rrule_str":   rrule_str,
            }

            if add_event_to_ics(self.ics_path, ev):
                dialog.close()
                self.events = parse_ics(self.ics_path)
                self._refresh()
            else:
                error_lbl.set_label("Erro ao salvar no arquivo ICS.")
                error_lbl.set_visible(True)

        save_btn.connect("clicked", on_save)
        dialog.present(self.win)

    # ── Delete event ─────────────────────────────────────────────────────────

    def _on_delete_event(self, ev: dict):
        uid = ev.get("uid", "")
        is_recurring = bool(ev.get("rrule"))

        if not uid:
            # No UID — cannot reliably delete; show message
            self._show_toast("Evento sem UID — não é possível deletar.")
            return

        if is_recurring:
            self._confirm_delete_recurring(ev)
        else:
            self._confirm_delete_simple(ev)

    def _confirm_delete_simple(self, ev: dict):
        dialog = Adw.AlertDialog(
            heading="Deletar evento",
            body=f"Remover \"{ev.get('summary', '')}\" permanentemente?",
        )
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("delete", "Deletar")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_dlg, response):
            if response == "delete":
                if delete_event_from_ics(self.ics_path, ev["uid"]):
                    self.events = parse_ics(self.ics_path)
                    self._refresh()
                else:
                    self._show_toast("Erro ao deletar o evento.")
        dialog.connect("response", on_response)
        dialog.present(self.win)

    def _confirm_delete_recurring(self, ev: dict):
        dialog = Adw.AlertDialog(
            heading="Deletar evento recorrente",
            body=f"\"{ev.get('summary', '')}\" se repete. O que deseja fazer?",
        )
        dialog.add_response("cancel",     "Cancelar")
        dialog.add_response("occurrence", "Só esta ocorrência")
        dialog.add_response("all",        "Todas as ocorrências")
        dialog.set_response_appearance("occurrence", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance("all",        Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_dlg, response):
            if response == "occurrence":
                if delete_event_from_ics(self.ics_path, ev["uid"], self.current_date):
                    self.events = parse_ics(self.ics_path)
                    self._refresh()
                else:
                    self._show_toast("Erro ao excluir a ocorrência.")
            elif response == "all":
                if delete_event_from_ics(self.ics_path, ev["uid"]):
                    self.events = parse_ics(self.ics_path)
                    self._refresh()
                else:
                    self._show_toast("Erro ao deletar o evento.")
        dialog.connect("response", on_response)
        dialog.present(self.win)

    def _show_toast(self, message: str):
        toast = Adw.Toast(title=message)
        toast.set_timeout(3)
        content = self.win.get_content()
        if isinstance(content, Adw.ToastOverlay):
            content.add_toast(toast)
        else:
            overlay = Adw.ToastOverlay()
            self.win.set_content(overlay)
            overlay.set_child(content)
            overlay.add_toast(toast)


def main():
    app = CalViewerApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())

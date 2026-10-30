#!/usr/bin/env python3
"""
mkvnote paths - fills the filename column of an mkvnote CSV.

A CSV exported from Airtable for mkvnote has every column filled except
filename, which must hold each file's full path on the JPCARCHIVE server.
This script finds each row's JPC_AV_xxxxx.mkv on the server and writes a
copy of the CSV with those paths filled in. It only reads the server: the
one file it writes is the new CSV.
"""

import argparse
import codecs
import csv
import datetime
import io
import os
import re
import stat
import sys

# ==============================
# TERMINAL COLORS
# ==============================

class Colors:
    """ANSI color codes for the report (stdout)."""
    BOLD = '\033[1m'
    DIM = '\033[2m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'

    @classmethod
    def disable(cls):
        """Disable colors (for non-TTY output)."""
        for attr in ['BOLD', 'DIM', 'GREEN', 'YELLOW', 'RED', 'RESET']:
            setattr(cls, attr, '')

# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()

# ==============================
# SETTINGS
# ==============================

DEFAULT_ROOT = "/Volumes/JPCARCHIVE/"

# Date folders (yyyymmdd) are looked for down to this many levels below the
# root: 00_from_dmz/upload/YYYY-MM/YYYYMMDD is 4 levels below JPCARCHIVE.
DATE_SCAN_DEPTH = 4

CATALOG_RE = re.compile(r"JPC_AV_[0-9]{5}")
# A folder named for a catalog number: the number itself, or the number
# followed by "_" (JPC_AV_01548_refid_<ref_id>). Such folders are never
# listed; only their <number>.mkv is looked up.
JPC_FOLDER_RE = re.compile(r"(JPC_AV_[0-9]{5})(?:_.*)?", re.DOTALL)
DATE_RE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")

# mkvnote can't use a path containing these: it puts each path inside a
# single-quoted XPath and reads the filename column line by line.
UNSAFE_PATH_CHARS = ("'", "\n", "\r")

# Exit statuses (see EXIT STATUS in the help)
EXIT_READY = 0        # saved; every row has its path
EXIT_ATTENTION = 1    # saved but not ready; or --verify-uniqueness could
                      # not read everything, so nothing was saved
EXIT_ERROR = 2        # nothing usable saved
EXIT_INTERRUPTED = 130

DESCRIPTION = """\
Fill in the filename column of an mkvnote CSV.

Reads a CSV exported from Airtable for mkvnote, finds each row's
JPC_AV_xxxxx.mkv on the JPCARCHIVE server, and writes a copy of the CSV
with each file's full path in the filename column. Completely blank rows
are dropped; every other cell is copied unchanged. The server is only
read: the one file written is the new CSV."""

EPILOG = f"""\
how files are found:
  Each .mkv is named after its row's CATALOG_NUMBER (JPC_AV_ and 5 digits)
  and sits directly in a folder with the same name, or a name starting
  with that number and "_" (JPC_AV_01548_refid_.../JPC_AV_01548.mkv).
  1. Date folders first: folders named yyyymmdd from DATE_DIGITIZED, up to
     {DATE_SCAN_DEPTH} levels below {DEFAULT_ROOT}
  2. Then the rest of the server, for rows not found in a date folder. The
     search stops once every row is found: one copy of each file is
     assumed unless --verify-uniqueness is given.
  Hidden folders (names starting with ".") and symlinked folders are
  never searched.

output:
  <csv name>_mkvnote-paths_<yyyymmdd_hhmmss>.csv next to the CSV, or in
  the -o folder. An existing file is never overwritten.

report:
  Lists the rows that need attention (not found, a missing, invalid or
  repeated catalog number, a path mkvnote can't use), then ends with:
    Ready for mkvnote: <file>   every row has its path
    NOT ready                   fix the rows listed first
    STOP (a big banner)         a filename already in the CSV does not
                                match the server, or a file was found
                                twice: a person must check those rows

exit status:
  0    saved and ready for mkvnote
  1    saved but NOT ready (rows need attention, or STOP); or, with
       --verify-uniqueness, folders could not be read - nothing saved
  2    no usable CSV: a problem with the arguments or the CSV,
       JPCARCHIVE not mounted, or the new CSV could not be written
       (a partial file that could not be deleted is named)
  130  interrupted (Ctrl-C); the message says whether the new CSV
       was saved, or names a partial file left behind

example:
  python3 mkvnote_paths.py ~/Downloads/jpc_mkvnote_b1.csv"""


class Stop(Exception):
    """A problem found before anything is written: the message is shown
    and the run exits 2."""


class Interrupted(Exception):
    """Ctrl-C while the new CSV was being written; carries any leftover
    file that could not be deleted."""

    def __init__(self, leftover):
        super().__init__(leftover)
        self.leftover = leftover


def describe(error):
    """A short reason for an exception, e.g. 'Permission denied'."""
    return getattr(error, "strerror", None) or str(error) or type(error).__name__


def plural(count, word, words=None):
    return f"{count} {word if count == 1 else (words or word + 's')}"


# ==============================
# READING THE CSV
# ==============================

def read_csv(path):
    """The CSV's header, its data records as (start line, cells) with
    completely blank records dropped, whether it had a BOM, and how many
    blank records were dropped. Any problem raises Stop."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise Stop(f"can't read {path}: {describe(e)}")
    had_bom = data.startswith(codecs.BOM_UTF8)
    if had_bom:
        data = data[len(codecs.BOM_UTF8):]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise Stop(f"{path} is not UTF-8 text (byte {e.start}); export it from Airtable as CSV again")

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    records = []
    start = 1
    try:
        for cells in reader:
            records.append((start, cells))
            start = reader.line_num + 1
    except csv.Error as e:
        raise Stop(f"the CSV can't be read at line {reader.line_num}: {e}")
    if not records:
        raise Stop("the CSV is empty")

    header = records[0][1]
    repeated = sorted({name for name in header if header.count(name) > 1})
    if repeated:
        raise Stop("the header repeats column name(s): " + ", ".join(repr(n) for n in repeated))
    if "filename" not in header:
        raise Stop("the CSV has no 'filename' column")
    # mkvnote takes any column that reads "filename" once underscores are
    # removed as its filename column, and the last one wins
    look_alikes = [n for n in header
                   if n != "filename" and n.replace("_", "").replace(" ", "") == "filename"]
    if look_alikes:
        raise Stop("mkvnote would read " + ", ".join(repr(n) for n in look_alikes)
                   + " as the filename column instead of 'filename'; rename or remove it")
    if "CATALOG_NUMBER" not in header:
        raise Stop("the CSV has no 'CATALOG_NUMBER' column")

    kept = []
    dropped = 0
    for line, cells in records[1:]:
        if all(not cell.strip() for cell in cells):
            dropped += 1
            continue
        if len(cells) != len(header):
            raise Stop(f"line {line}: the row has {len(cells)} cells but the header has {len(header)}")
        kept.append((line, cells))
    if not kept:
        raise Stop("No rows to process: the CSV has only a header or blank rows")
    return header, kept, had_bom, dropped


def parse_date(value):
    """'2024-09-20' -> '20240920'; None for an empty or invalid date."""
    match = DATE_RE.fullmatch(value.strip())
    if not match:
        return None
    try:
        datetime.date(int(match[1]), int(match[2]), int(match[3]))
    except ValueError:
        return None
    return match[1] + match[2] + match[3]


class Row:
    """One data row of the CSV and what the search made of it."""

    def __init__(self, line, cells, filename_col, catalog_col, date_col):
        self.line = line                  # CSV line where the record starts
        self.cells = cells
        self.filename_col = filename_col
        self.catalog = cells[catalog_col].strip()
        self.valid = bool(CATALOG_RE.fullmatch(self.catalog))
        self.existing = cells[filename_col].strip()   # "" when empty
        self.date = parse_date(cells[date_col]) if date_col is not None else None
        self.same_catalog_lines = []      # other rows with this catalog number
        self.matches = []
        self.found_by = None              # the pass that found it: 1 or 2
        self.outcome = None               # found, confirmed, attention, serious
        self.reason = ""
        self.details = []

    @property
    def searchable(self):
        return self.valid and not self.same_catalog_lines


# ==============================
# SEARCHING THE SERVER (read-only)
# ==============================

class Progress:
    """One updating line on stderr while searching, when it is a terminal."""

    def __init__(self):
        self.on = sys.stderr.isatty()
        self.shown = False

    def update(self, label, count):
        if self.on and count % 25 == 0:
            sys.stderr.write(f"\r  searching {label}: {count} folders ")
            sys.stderr.flush()
            self.shown = True

    def clear(self):
        if self.shown:
            sys.stderr.write("\r" + " " * 60 + "\r")
            sys.stderr.flush()
            self.shown = False


class Search:
    """Finds <catalog>.mkv files under the root. Every listing goes through
    listing(), which never shows hidden entries, and records every error
    instead of taking it as an empty folder."""

    def __init__(self, root, progress):
        self.root = root
        self.progress = progress
        self.label = ""
        self.listed = 0
        self.errors = []      # (path, reason)
        self.notes = {}       # catalog -> notes for the report

    def error(self, path, error):
        problem = (path, describe(error))
        if problem not in self.errors:      # both passes may meet it
            self.errors.append(problem)

    def note(self, catalog, text):
        notes = self.notes.setdefault(catalog, [])
        if text not in notes:
            notes.append(text)

    def listing(self, folder):
        """The folder's entries as (name, path, kind), sorted by name; kind
        is 'dir', 'link' or 'other'. Hidden names are dropped before
        anything else looks at them."""
        self.listed += 1
        self.progress.update(self.label, self.listed)
        entries = []
        try:
            with os.scandir(folder) as found:
                for entry in found:
                    if entry.name.startswith("."):
                        continue
                    try:
                        if entry.is_symlink():
                            kind = "link"
                        elif entry.is_dir(follow_symlinks=False):
                            kind = "dir"
                        else:
                            kind = "other"
                    except OSError as e:
                        self.error(entry.path, e)
                        continue
                    entries.append((entry.name, entry.path, kind))
        except OSError as e:
            self.error(folder, e)
        entries.sort()
        return entries

    def check(self, folder, catalog):
        """The path of catalog.mkv in this JPC folder if it is a regular
        file, else None. The folder itself is never listed."""
        path = os.path.join(folder, catalog + ".mkv")
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            self.note(catalog, f"{folder} has no {catalog}.mkv")
            return None
        except OSError as e:
            self.error(path, e)
            return None
        if stat.S_ISREG(info.st_mode):
            return path
        self.note(catalog, f"{path} is not a regular file (a symlink or other); ignored")
        return None

    def jpc_entry(self, name, path, kind, wanted, found):
        """Check one listing entry that may be a JPC folder for a wanted
        catalog number; matches are added to found. -> its catalog number
        when it is a match, else None."""
        named = JPC_FOLDER_RE.fullmatch(name)
        if not named or named.group(1) not in wanted:
            return None
        catalog = named.group(1)
        if kind == "link":
            self.note(catalog, f"{path} is a symlinked folder; not followed")
        elif kind == "dir":
            hit = self.check(path, catalog)
            if hit:
                found.setdefault(catalog, []).append(hit)
                return catalog
        return None

    def date_pass(self, catalogs_by_date):
        """Pass 1: look in folders named yyyymmdd for each row's date, down
        to DATE_SCAN_DEPTH levels below the root. -> {catalog: [paths]}"""
        self.label = "date folders"
        date_folders = {}
        level = [self.root]
        for depth in range(1, DATE_SCAN_DEPTH + 1):
            below = []
            for folder in level:
                for name, path, kind in self.listing(folder):
                    if kind != "dir" or JPC_FOLDER_RE.fullmatch(name):
                        continue
                    if name in catalogs_by_date:
                        date_folders.setdefault(name, []).append(path)
                    below.append(path)
            level = below
        found = {}
        for date, folders in sorted(date_folders.items()):
            for folder in folders:
                for name, path, kind in self.listing(folder):
                    self.jpc_entry(name, path, kind, catalogs_by_date[date], found)
        return found

    def full_pass(self, wanted, first_only):
        """Pass 2: search everything under the root, depth first in name
        order. With first_only, a catalog number is done at its first match
        and the search stops once all are done. -> {catalog: [paths]}"""
        self.label = "the server"
        remaining = set(wanted)
        found = {}
        stack = [self.root]
        while stack and remaining:
            folder = stack.pop()
            subfolders = []
            for name, path, kind in self.listing(folder):
                if JPC_FOLDER_RE.fullmatch(name):
                    hit = self.jpc_entry(name, path, kind, remaining, found)
                    if hit and first_only:
                        remaining.discard(hit)
                    continue        # JPC folders are never entered
                if kind == "dir":
                    subfolders.append(path)
            stack.extend(reversed(subfolders))
        return found


def check_root(root):
    """The root must exist, be a folder and be listable; else Stop."""
    try:
        info = os.stat(root)
    except FileNotFoundError:
        raise Stop(f"{root} not found - is JPCARCHIVE mounted? (or is --root wrong?)")
    except OSError as e:
        raise Stop(f"can't reach {root}: {describe(e)}")
    if not stat.S_ISDIR(info.st_mode):
        raise Stop(f"{root} is not a folder")
    try:
        with os.scandir(root) as found:
            next(iter(found), None)
    except OSError as e:
        raise Stop(f"can't list {root}: {describe(e)}")


# ==============================
# DECIDING EACH ROW
# ==============================

def unsafe(path):
    return any(char in path for char in UNSAFE_PATH_CHARS)


def decide(row, search):
    """Set the row's outcome; the first rule that applies wins. Only a
    found or confirmed row gets a new filename."""
    def result(outcome, reason, *details):
        row.outcome, row.reason, row.details = outcome, reason, list(details)

    if not row.valid:
        if not row.catalog:
            return result("attention", "no CATALOG_NUMBER")
        return result("attention", f"{row.catalog!r} is not a catalog number (JPC_AV_ and 5 digits)")
    if row.same_catalog_lines:
        lines = ", ".join(str(n) for n in row.same_catalog_lines)
        return result("attention", f"the same catalog number is also on line(s) {lines}; each row needs its own")
    paths = row.matches
    if row.existing:
        if len(paths) == 1 and paths[0] == row.existing:
            if unsafe(paths[0]):
                return result("attention", "mkvnote can't use this path (it has ' or a line break)", paths[0])
            row.cells[row.filename_col] = paths[0]
            return result("confirmed", "")
        found = [f"found:       {p}" for p in paths] or ["found:       nothing on the server"]
        return result("serious", "the filename already in the CSV does not match the server",
                      f"in the CSV:  {row.existing}", *found)
    if not paths:
        details = list(search.notes.get(row.catalog, []))
        if search.errors:
            details.append(f"{plural(len(search.errors), 'folder')} could not be read; it may be in one of them")
        return result("attention", "not found on the server", *details)
    if len(paths) > 1:
        return result("serious", f"found {len(paths)} copies on the server", *paths)
    if unsafe(paths[0]):
        return result("attention", "mkvnote can't use this path (it has ' or a line break)", paths[0])
    row.cells[row.filename_col] = paths[0]
    return result("found", "")


# ==============================
# WRITING THE NEW CSV
# ==============================

def remove_created(path):
    """Delete the partly written output this run created. -> None, or the
    leftover file and why it could not be deleted."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        return None
    except OSError as e:
        return f"{path} ({describe(e)})"
    return None


def write_output(path, header, rows, had_bom):
    """Write the new CSV. -> None when saved, else why not. An existing
    file is never overwritten or deleted."""
    try:
        out = open(path, "x", encoding="utf-8-sig" if had_bom else "utf-8", newline="")
    except FileExistsError:
        return f"{path} already exists (it was not touched); run the script again"
    except OSError as e:
        return f"can't create {path}: {describe(e)}"
    try:
        with out:
            writer = csv.writer(out, lineterminator="\n")
            writer.writerow(header)
            for row in rows:
                writer.writerow(row.cells)
    except KeyboardInterrupt:
        raise Interrupted(remove_created(path))
    except (OSError, ValueError, csv.Error) as e:
        leftover = remove_created(path)
        why = f"writing {path} failed: {describe(e)}"
        if leftover:
            why += f". A partial file was left at {leftover} - delete it"
        return why
    except BaseException:
        remove_created(path)
        raise
    return None


# ==============================
# REPORT
# ==============================

def print_row(row):
    print(f"  line {row.line:<5} {row.catalog or '(none)':<13} {row.reason}")
    for detail in row.details:
        print(f"{'':26}{detail}")


def print_report(csv_path, root, verify, has_date, rows, dropped, search, out_path, problem):
    C = Colors
    by = {}
    for row in rows:
        by.setdefault(row.outcome, []).append(row)
    found = by.get("found", [])
    attention = by.get("attention", [])
    serious = by.get("serious", [])

    print(f"{C.BOLD}mkvnote paths{C.RESET}")
    print(f"  CSV:     {csv_path}")
    mode = "checking for duplicate copies" if verify else "one copy of each file assumed"
    print(f"  Search:  {root} ({mode})")
    if not has_date and not verify:
        print(f"  {C.DIM}No DATE_DIGITIZED column: the date-folder pass was skipped{C.RESET}")
    print()
    blank = f" ({plural(dropped, 'blank row')} dropped)" if dropped else ""
    print(f"Rows: {len(rows)}{blank}")
    print(f"  found in a date folder:     {sum(1 for r in found if r.found_by == 1)}")
    print(f"  found elsewhere:            {sum(1 for r in found if r.found_by == 2)}")
    print(f"  already filled, confirmed:  {len(by.get('confirmed', []))}")
    print(f"  need attention:             {len(attention)}")
    print(f"  STOP, a person must check:  {len(serious)}")

    if search.errors:
        print()
        print(f"{C.YELLOW}Warning: {plural(len(search.errors), 'folder or entry', 'folders or entries')} could not be read:{C.RESET}")
        for path, why in search.errors:
            print(f"  {path} - {why}")

    if attention:
        print()
        print(f"{C.YELLOW}Rows needing attention:{C.RESET}")
        for row in attention:
            print_row(row)

    print()
    if problem:
        print(f"{C.RED}NOT saved:{C.RESET} {problem}")
    else:
        print(f"Saved: {out_path}")

    if serious:
        text = f"STOP: {plural(len(serious), 'row needs', 'rows need')} a person before this CSV goes to mkvnote"
        middle = f"!!  {text}  !!"
        border = "!" * len(middle)
        print()
        print(f"{C.RED}{C.BOLD}{border}")
        print(middle)
        print(f"{border}{C.RESET}")
        for row in serious:
            print_row(row)
        if attention:
            print(f"  Also {plural(len(attention), 'other row needs', 'other rows need')} attention (listed above).")
    elif problem:
        pass                # "NOT saved" above is the last word
    elif attention:
        print(f"{C.YELLOW}NOT ready:{C.RESET} {plural(len(attention), 'row needs', 'rows need')} "
              f"attention (listed above). Do not run mkvnote with this CSV yet.")
    else:
        print(f"{C.GREEN}Ready for mkvnote:{C.RESET} {out_path}")


# ==============================
# MAIN
# ==============================

def run(args, progress):
    started = datetime.datetime.now()

    # 1. Arguments
    csv_path = os.path.abspath(args.csv)
    try:
        info = os.stat(csv_path)
    except FileNotFoundError:
        raise Stop(f"CSV not found: {csv_path}")
    except OSError as e:
        raise Stop(f"can't read {csv_path}: {describe(e)}")
    if not stat.S_ISREG(info.st_mode):
        raise Stop(f"not a file: {csv_path}")
    if args.output is not None:
        out_dir = os.path.abspath(args.output)
        try:
            info = os.stat(out_dir)
        except FileNotFoundError:
            raise Stop(f"-o folder not found: {out_dir}")
        except OSError as e:
            raise Stop(f"can't use -o folder {out_dir}: {describe(e)}")
        if not stat.S_ISDIR(info.st_mode):
            raise Stop(f"-o must be a folder: {out_dir}")
    else:
        out_dir = os.path.dirname(csv_path)
    stem = os.path.splitext(os.path.basename(csv_path))[0]
    out_path = os.path.join(out_dir, f"{stem}_mkvnote-paths_{started:%Y%m%d_%H%M%S}.csv")

    # 2. The CSV
    header, records, had_bom, dropped = read_csv(csv_path)
    has_date = "DATE_DIGITIZED" in header
    rows = [Row(line, cells, header.index("filename"), header.index("CATALOG_NUMBER"),
                header.index("DATE_DIGITIZED") if has_date else None)
            for line, cells in records]
    by_catalog = {}
    for row in rows:
        if row.valid:
            by_catalog.setdefault(row.catalog, []).append(row)
    for same in by_catalog.values():
        for row in same:
            row.same_catalog_lines = [r.line for r in same if r is not row]

    # 3. The root
    root = os.path.abspath(args.root)
    check_root(root)

    # 4. The search
    search = Search(root, progress)
    searchable = [row for row in rows if row.searchable]
    if not args.verify_uniqueness:
        catalogs_by_date = {}
        for row in searchable:
            if row.date:
                catalogs_by_date.setdefault(row.date, set()).add(row.catalog)
        if catalogs_by_date:
            first = search.date_pass(catalogs_by_date)
            for row in searchable:
                if row.catalog in first:
                    row.matches, row.found_by = first[row.catalog], 1
    wanted = {row.catalog for row in searchable if row.found_by is None}
    if wanted:
        second = search.full_pass(wanted, first_only=not args.verify_uniqueness)
        for row in searchable:
            if row.found_by is None and row.catalog in second:
                row.matches, row.found_by = second[row.catalog], 2
    progress.clear()

    # 5. Each row
    for row in rows:
        decide(row, search)

    # 6. The new CSV
    if args.verify_uniqueness and search.errors:
        problem = (f"{plural(len(search.errors), 'folder or entry', 'folders or entries')} could not be "
                   f"read, so duplicate copies can't be ruled out")
        code = EXIT_ATTENTION
    else:
        problem = write_output(out_path, header, rows, had_bom)
        if not problem:
            args.saved_to = out_path
        if problem:
            code = EXIT_ERROR
        elif any(row.outcome in ("attention", "serious") for row in rows):
            code = EXIT_ATTENTION
        else:
            code = EXIT_READY

    # 7. Report
    print_report(csv_path, root, args.verify_uniqueness, has_date, rows, dropped,
                 search, out_path, problem)
    return code


def build_parser():
    parser = argparse.ArgumentParser(
        prog="mkvnote_paths.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=DESCRIPTION,
        epilog=EPILOG)
    parser.add_argument("csv", metavar="CSV",
                        help="the CSV exported from Airtable for mkvnote")
    parser.add_argument("--root", metavar="DIR", default=DEFAULT_ROOT,
                        help=f"search here instead of {DEFAULT_ROOT}")
    parser.add_argument("-o", dest="output", metavar="FOLDER",
                        help="write the new CSV into FOLDER instead of next to the CSV")
    parser.add_argument("--verify-uniqueness", action="store_true",
                        help="search the whole server for every row and flag any "
                             "file found more than once (slower)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    progress = Progress()
    try:
        return run(args, progress)
    except Stop as e:
        progress.clear()
        print(f"Error: {e}", file=sys.stderr)
        print("Nothing was written.", file=sys.stderr)
        return EXIT_ERROR
    except Interrupted as e:
        progress.clear()
        print("\nInterrupted (Ctrl-C). The new CSV was not saved.", file=sys.stderr)
        if e.leftover:
            print(f"A partial file was left at {e.leftover} - delete it.", file=sys.stderr)
        return EXIT_INTERRUPTED
    except KeyboardInterrupt:
        progress.clear()
        saved = getattr(args, "saved_to", None)
        print("\nInterrupted (Ctrl-C). " + (f"The new CSV was saved: {saved}" if saved
                                           else "Nothing was saved."), file=sys.stderr)
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(main())

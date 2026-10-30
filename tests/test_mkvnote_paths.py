#!/usr/bin/env python3
"""Focused tests for mkvnote_paths.py - standard library only.

Every case runs the script as a separate process on an invented CSV and a
synthetic folder tree standing in for the server, in a private temporary
folder; the CSV and the new CSV sit outside that tree. The script runs
inside a small wrapper (no test hooks in the script itself) that:
  - stops the child at once, with exit 99, if anything touches
    /Volumes/JPCARCHIVE, so no test can reach the real server;
  - logs every folder the script lists and every entry it classifies;
  - injects the faults a test names (an I/O error classifying an entry, a
    listing or lstat error, a failing write, close or delete, a pause in a
    listing) and logs each one that fires.
The .mkv files are placeholders of a few bytes, so these tests say nothing
about SMB, the real server's layout or its speed.

    python3 tests/test_mkvnote_paths.py          # from the repository folder

MKVNOTE_PATHS_SCRIPT=/path/to/other/version.py runs the same checks against
another copy of the script.
"""

import csv
import hashlib
import io
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get("MKVNOTE_PATHS_SCRIPT",
                        os.path.join(os.path.dirname(HERE), "mkvnote_paths.py"))

WRAPPER = r'''
import builtins, errno, json, os, runpy, signal, sys, time

LOG = os.environ["MP_LOG"]
FAULTS = json.loads(os.environ.get("MP_FAULTS") or "{}")
GUARD = "/volumes/jpcarchive"
real_open, real_scandir = builtins.open, os.scandir
real_stat, real_lstat, real_unlink = os.stat, os.lstat, os.unlink

def log(kind, path):
    with real_open(LOG, "a") as f:
        f.write(json.dumps([kind, path]) + "\n")

def text(path):
    return path if isinstance(path, str) else os.fsdecode(path)

def guard(path):
    if isinstance(path, int):
        return
    full = os.path.abspath(text(path))
    if full.lower() == GUARD or full.lower().startswith(GUARD + "/"):
        log("BLOCKED", full)
        os._exit(99)

def fault(kind, path, error, message):
    log("FAULT " + kind, path)
    raise OSError(error, message + " (injected)", path)

class Entry:
    def __init__(self, entry):
        self._entry, self.name, self.path = entry, entry.name, entry.path
    def _classify(self):
        log("classify", self.path)
        if self.path in FAULTS.get("classify", []):
            fault("classify", self.path, errno.EIO, "Input/output error")
    def is_symlink(self):
        self._classify()
        return self._entry.is_symlink()
    def is_dir(self, *, follow_symlinks=True):
        self._classify()
        return self._entry.is_dir(follow_symlinks=follow_symlinks)
    def is_file(self, *, follow_symlinks=True):
        self._classify()
        return self._entry.is_file(follow_symlinks=follow_symlinks)
    def stat(self, *, follow_symlinks=True):
        self._classify()
        return self._entry.stat(follow_symlinks=follow_symlinks)
    def __fspath__(self):
        return self.path

class Listing:
    def __init__(self, entries):
        self._entries = entries
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        self._entries.close()
    def close(self):
        self._entries.close()
    def __iter__(self):
        return self
    def __next__(self):
        return Entry(next(self._entries))

def scandir(path="."):
    guard(path)
    log("list", text(path))
    if text(path) in FAULTS.get("list", []):
        fault("list", text(path), errno.EACCES, "Permission denied")
    if text(path) in FAULTS.get("pause", []):
        log("PAUSED", text(path))
        time.sleep(30)
    return Listing(real_scandir(path))

def stat_(path, *a, **k):
    guard(path)
    return real_stat(path, *a, **k)

def lstat_(path, *a, **k):
    guard(path)
    if text(path) in FAULTS.get("lstat", []):
        fault("lstat", text(path), errno.EIO, "Input/output error")
    return real_lstat(path, *a, **k)

def unlink_(path, *a, **k):
    guard(path)
    if FAULTS.get("unlink") and "_mkvnote-paths_" in text(path):
        fault("unlink", text(path), errno.EACCES, "Permission denied")
    return real_unlink(path, *a, **k)

class FaultyFile:
    def __init__(self, f, kind):
        self._f, self._kind, self._writes = f, kind, 0
    def write(self, s):
        self._writes += 1
        if self._kind == "write" and self._writes == 2:
            fault("write", self._f.name, errno.ENOSPC, "No space left on device")
        return self._f.write(s)
    def close(self):
        self._f.close()
        if self._kind == "close":
            self._kind = None
            fault("close", self._f.name, errno.EIO, "Input/output error")
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        self.close()
        return False
    def __getattr__(self, name):
        return getattr(self._f, name)

def open_(file, mode="r", *a, **k):
    guard(file)
    f = real_open(file, mode, *a, **k)
    if isinstance(file, str) and "_mkvnote-paths_" in os.path.basename(file) and "x" in mode:
        for kind in ("write", "close"):
            if FAULTS.get(kind):
                return FaultyFile(f, kind)
    return f

# A real SIGINT must raise KeyboardInterrupt even if this child was started
# with SIGINT ignored (Python keeps an inherited SIG_IGN)
signal.signal(signal.SIGINT, signal.default_int_handler)
os.scandir, os.stat, os.lstat, os.unlink = scandir, stat_, lstat_, unlink_
builtins.open = open_
script = sys.argv[1]
sys.argv = [script] + sys.argv[2:]
runpy.run_path(script, run_name="__main__")
'''

BOM = "﻿"
NAME_RE = re.compile(r"^(?P<stem>.+)_mkvnote-paths_(?P<ts>\d{8}_\d{6})\.csv$")
HEADER = ["filename", "CATALOG_NUMBER", "TITLE", "DATE_DIGITIZED"]
JPC_NAME = re.compile(r"JPC_AV_[0-9]{5}(_.*)?")

# Invented, with the shape of a real Airtable export: a BOM, multi-line
# quoted cells, quoted commas and quotes, a whitespace-only filename, a
# catalog number with a trailing space, and blank rows at the end.
FIXTURE = (
    BOM + "filename,CATALOG_NUMBER,COLLECTION,TITLE,DESCRIPTION,DATE_DIGITIZED,"
    "ENCODER_SETTINGS,ENCODED_BY,_TRANSFER_NOTES\n"
    ',JPC_AV_00001,Test Collection,"Sample Show, Episode #1","Line one\n'
    'Line two with ""quotes""",2024-09-20,"VTR: Example ;\n'
    'TBC: Example",Example Org,\n'
    " ,JPC_AV_00002 ,Test Collection,Plain title,,2024-09-11,,,Note\n"
    ',JPC_AV_00003,Test Collection,"Title, with comma",,2025-03-24,,"""Quoted Org""",\n'
    ",,,,,,,,\n"
    ",,,,,,,,\n"
)


def date_dir(date):
    """'2024-09-20' -> the known layout's folder for that date."""
    return f"00_from_dmz/upload/{date[:7]}/{date.replace('-', '')}"


def parse(text):
    return list(csv.reader(io.StringIO(text, newline="")))


def snapshot(top):
    """Every entry under top: type, and content hash or link target."""
    state = {}
    for dirpath, dirnames, filenames in os.walk(top):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            info = os.lstat(path)
            rel = os.path.relpath(path, top)
            if stat.S_ISLNK(info.st_mode):
                state[rel] = ("link", os.readlink(path))
            elif stat.S_ISDIR(info.st_mode):
                state[rel] = ("dir",)
            else:
                with open(path, "rb") as f:
                    state[rel] = ("file", hashlib.sha256(f.read()).hexdigest())
    return state


class Run:
    def __init__(self, proc, log, outputs):
        self.code = proc.returncode
        self.out = proc.stdout
        self.err = proc.stderr
        self.log = log
        self.outputs = outputs

    @property
    def text(self):
        return f"exit {self.code}\n--- stdout\n{self.out}\n--- stderr\n{self.err}"

    def logged(self, kind):
        return [path for k, path in self.log if k == kind]

    def fired(self, kind):
        return bool(self.logged("FAULT " + kind))


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="mkvnote-paths-test-"))
        self.server = os.path.join(self.tmp, "server")
        self.work = os.path.join(self.tmp, "work")
        self.home = os.path.join(self.tmp, "home")
        self.temp = os.path.join(self.tmp, "temp")
        for folder in (self.server, self.work, self.home, self.temp):
            os.makedirs(folder)
        self.wrapper = os.path.join(self.tmp, "wrapper.py")
        with open(self.wrapper, "w") as f:
            f.write(WRAPPER)
        self.logfile = os.path.join(self.tmp, "wrapper.log")
        self.locked = []

    def tearDown(self):
        for path in self.locked:
            os.chmod(path, 0o755)
        shutil.rmtree(self.tmp)

    # --- building the synthetic server and CSV

    def mkv(self, rel):
        path = os.path.join(self.server, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"placeholder " + rel.encode())
        return path

    def folder(self, rel):
        path = os.path.join(self.server, rel)
        os.makedirs(path, exist_ok=True)
        return path

    def lock(self, path):
        if os.geteuid() == 0:
            self.skipTest("permissions are not enforced for root")
        os.chmod(path, 0)
        self.locked.append(path)

    def write_csv(self, rows, header=HEADER, bom=True, name="batch.csv"):
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
        return self.write_raw((BOM if bom else "") + buf.getvalue(), name)

    def write_raw(self, content, name="batch.csv"):
        path = os.path.join(self.work, name)
        with open(path, "wb") as f:
            f.write(content if isinstance(content, bytes) else content.encode("utf-8"))
        return path

    @staticmethod
    def row(catalog, date="", filename="", title="Title"):
        return [filename, catalog, title, date]

    # --- running

    def run_script(self, *args, root=True, faults=None):
        if os.path.exists(self.logfile):
            os.unlink(self.logfile)
        env = {"PATH": "/usr/bin:/bin", "HOME": self.home, "TMPDIR": self.temp,
               "LANG": "en_US.UTF-8", "MP_LOG": self.logfile,
               "MP_FAULTS": json.dumps(faults or {})}
        cmd = [sys.executable, self.wrapper, SCRIPT] + list(args)
        if root:
            cmd += ["--root", self.server]
        proc = subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=120)
        return Run(proc, self.read_log(), self.outputs())

    def read_log(self):
        if not os.path.exists(self.logfile):
            return []
        with open(self.logfile) as f:
            return [json.loads(line) for line in f]

    def outputs(self, folder=None):
        return sorted(name for name in os.listdir(folder or self.work)
                      if "_mkvnote-paths_" in name)

    def clear_outputs(self):
        """Before a second run in one test: the same second would give the
        same output name, which the script rightly refuses."""
        for name in self.outputs():
            os.unlink(os.path.join(self.work, name))

    def only_output(self, run, folder=None):
        self.assertEqual(len(run.outputs if folder is None else self.outputs(folder)), 1, run.text)
        name = (run.outputs if folder is None else self.outputs(folder))[0]
        return os.path.join(folder or self.work, name)

    def read_output(self, path):
        with open(path, "rb") as f:
            data = f.read()
        return data, parse(data.decode("utf-8-sig"))

    def filenames(self, run):
        """The filename column of the new CSV, by catalog number."""
        _, rows = self.read_output(self.only_output(run))
        col, cat = rows[0].index("filename"), rows[0].index("CATALOG_NUMBER")
        return {r[cat].strip(): r[col] for r in rows[1:]}

    def rel(self, path):
        return os.path.relpath(path, self.server)


class HappyPathTests(Base):

    def test_airtable_shaped_batch_round_trips_with_paths_filled(self):
        paths = {"JPC_AV_00001": self.mkv(date_dir("2024-09-20") + "/JPC_AV_00001/JPC_AV_00001.mkv"),
                 "JPC_AV_00002": self.mkv(date_dir("2024-09-11") + "/JPC_AV_00002/JPC_AV_00002.mkv"),
                 "JPC_AV_00003": self.mkv(date_dir("2025-03-24") + "/JPC_AV_00003/JPC_AV_00003.mkv")}
        csv_path = self.write_raw(FIXTURE)
        tree_before = snapshot(self.server)
        start = datetime.now().replace(microsecond=0)
        run = self.run_script(csv_path)
        end = datetime.now()
        self.assertEqual(run.code, 0, run.text)
        self.assertIn("found in a date folder:     3", run.out)
        self.assertIn("2 blank rows dropped", run.out)
        self.assertTrue(run.out.rstrip().splitlines()[-1].startswith("Ready for mkvnote:"), run.text)

        out = self.only_output(run)
        named = NAME_RE.match(os.path.basename(out))
        self.assertTrue(named, out)
        self.assertEqual(named.group("stem"), "batch")
        stamp = datetime.strptime(named.group("ts"), "%Y%m%d_%H%M%S")
        self.assertTrue(start <= stamp <= end, (start, stamp, end))

        data, rows = self.read_output(out)
        self.assertTrue(data.startswith(BOM.encode()), "the BOM must be kept")
        self.assertNotIn(b"\r", data)
        expected = parse(FIXTURE[1:])[:4]          # header + 3 rows, blanks dropped
        for row in expected[1:]:
            row[0] = paths[row[1].strip()]
        self.assertEqual(rows, expected)
        self.assertEqual(rows[2][1], "JPC_AV_00002 ", "other cells are copied unchanged")

        with open(csv_path, "rb") as f:
            self.assertEqual(f.read(), FIXTURE.encode(), "the input CSV must not change")
        self.assertEqual(snapshot(self.server), tree_before, "the server tree must not change")

    def test_no_bom_in_no_bom_out(self):
        self.mkv(date_dir("2024-09-20") + "/JPC_AV_00004/JPC_AV_00004.mkv")
        run = self.run_script(self.write_csv([self.row("JPC_AV_00004", "2024-09-20")], bom=False))
        self.assertEqual(run.code, 0, run.text)
        data, _ = self.read_output(self.only_output(run))
        self.assertFalse(data.startswith(BOM.encode()))

    def test_report_names_the_starting_line_after_multiline_cells(self):
        self.mkv(date_dir("2024-09-20") + "/JPC_AV_00001/JPC_AV_00001.mkv")
        self.mkv(date_dir("2025-03-24") + "/JPC_AV_00003/JPC_AV_00003.mkv")
        run = self.run_script(self.write_raw(FIXTURE))      # JPC_AV_00002 is missing
        self.assertEqual(run.code, 1, run.text)
        self.assertRegex(run.out, r"line 5 +JPC_AV_00002 +not found on the server")
        self.assertIn("NOT ready: 1 row needs attention", run.out)


class SearchPassTests(Base):

    def test_file_outside_its_date_folder_is_found_in_pass_2(self):
        self.folder(date_dir("2024-09-20"))
        path = self.mkv("elsewhere/archive/JPC_AV_00010/JPC_AV_00010.mkv")
        run = self.run_script(self.write_csv([self.row("JPC_AV_00010", "2024-09-20")]))
        self.assertEqual(run.code, 0, run.text)
        self.assertIn("found elsewhere:            1", run.out)
        self.assertEqual(self.filenames(run)["JPC_AV_00010"], path)

    def test_missing_or_bad_dates_still_find_the_file(self):
        paths = {c: self.mkv(f"misc/{c}/{c}.mkv") for c in ("JPC_AV_00013", "JPC_AV_00014", "JPC_AV_00015")}
        rows = [self.row("JPC_AV_00013", ""), self.row("JPC_AV_00014", "2024-02-30"),
                self.row("JPC_AV_00015", "09/20/2024")]
        run = self.run_script(self.write_csv(rows))
        self.assertEqual(run.code, 0, run.text)
        self.assertEqual(self.filenames(run), paths)

        no_date = self.write_csv([["", "JPC_AV_00013", "T"]], header=["filename", "CATALOG_NUMBER", "TITLE"],
                                 name="nodate.csv")
        run = self.run_script(no_date)
        self.assertEqual(run.code, 0, run.text)
        self.assertIn("No DATE_DIGITIZED column", run.out)

    def test_refid_folder_is_found(self):
        path = self.mkv(date_dir("2024-07-17") + "/JPC_AV_00011_refid_06e8/JPC_AV_00011.mkv")
        run = self.run_script(self.write_csv([self.row("JPC_AV_00011", "2024-07-17")]))
        self.assertEqual(run.code, 0, run.text)
        self.assertEqual(self.filenames(run)["JPC_AV_00011"], path)

    def test_date_folder_deeper_than_the_scan_falls_to_pass_2(self):
        path = self.mkv("a/b/c/d/20240920/JPC_AV_00012/JPC_AV_00012.mkv")
        run = self.run_script(self.write_csv([self.row("JPC_AV_00012", "2024-09-20")]))
        self.assertEqual(run.code, 0, run.text)
        self.assertIn("found elsewhere:            1", run.out)
        self.assertEqual(self.filenames(run)["JPC_AV_00012"], path)


class MatchingTests(Base):

    def test_only_catalog_mkv_directly_in_its_own_folder_matches(self):
        day = date_dir("2024-09-20")
        self.mkv(day + "/JPC_AV_00020.mkv")                       # loose, no JPC folder
        self.mkv(day + "/JPC_AV_000211/JPC_AV_00021.mkv")         # 6-digit folder name
        self.folder(day + "/JPC_AV_00022")                        # JPC folder, no .mkv
        rows = [self.row(c, "2024-09-20") for c in ("JPC_AV_00020", "JPC_AV_00021", "JPC_AV_00022")]
        run = self.run_script(self.write_csv(rows))
        self.assertEqual(run.code, 1, run.text)
        for catalog in ("JPC_AV_00020", "JPC_AV_00021", "JPC_AV_00022"):
            self.assertRegex(run.out, catalog + r" +not found on the server")
        self.assertIn(f"{self.server}/{day}/JPC_AV_00022 has no JPC_AV_00022.mkv", run.out)
        self.assertEqual(set(self.filenames(run).values()), {""})

    def test_catalog_numbers_must_have_exactly_5_digits(self):
        self.mkv("x/JPC_AV_0001/JPC_AV_0001.mkv")
        self.mkv("x/JPC_AV_000001/JPC_AV_000001.mkv")
        run = self.run_script(self.write_csv([self.row("JPC_AV_0001"), self.row("JPC_AV_000001")]))
        self.assertEqual(run.code, 1, run.text)
        self.assertIn("'JPC_AV_0001' is not a catalog number", run.out)
        self.assertIn("'JPC_AV_000001' is not a catalog number", run.out)


class NeverEnteredTests(Base):

    def test_jpc_folders_are_never_listed(self):
        day = date_dir("2024-09-20")
        self.mkv(day + "/JPC_AV_00030/JPC_AV_00030.mkv")
        self.mkv(day + "/JPC_AV_00030/sub/inner.txt")
        self.mkv("other/JPC_AV_09999_refid_x/deeper/JPC_AV_00031/JPC_AV_00031.mkv")
        rows = [self.row("JPC_AV_00030", "2024-09-20"), self.row("JPC_AV_00031")]
        for mode in ([], ["--verify-uniqueness"]):
            self.clear_outputs()
            run = self.run_script(self.write_csv(rows), *mode)
            self.assertEqual(run.code, 1, run.text)       # JPC_AV_00031 is nested: not found
            listed = [os.path.basename(p) for p in run.logged("list")]
            self.assertTrue(listed, run.text)
            self.assertFalse([n for n in listed if JPC_NAME.fullmatch(n)], listed)

    def test_hidden_entries_are_never_listed_or_classified(self):
        day = date_dir("2024-09-20")
        self.mkv(day + "/JPC_AV_00032/JPC_AV_00032.mkv")
        self.mkv(".zfs/snapshot/daily/" + day + "/JPC_AV_00032/JPC_AV_00032.mkv")
        self.mkv(".Trashes/501/JPC_AV_00032/JPC_AV_00032.mkv")
        self.mkv(day + "/.hidden_copy/JPC_AV_00032/JPC_AV_00032.mkv")
        self.lock(self.folder(".private"))
        run = self.run_script(self.write_csv([self.row("JPC_AV_00032", "2024-09-20")]),
                              "--verify-uniqueness")
        self.assertEqual(run.code, 0, run.text)           # one copy, no warnings
        self.assertNotIn("could not be read", run.out)
        touched = run.logged("list") + run.logged("classify")
        self.assertTrue(run.logged("classify"), run.text)
        hidden = [p for p in touched
                  if any(part.startswith(".") for part in self.rel(p).split(os.sep) if part != ".")]
        self.assertEqual(hidden, [])

    def test_symlinked_folders_are_never_entered(self):
        elsewhere = os.path.join(self.tmp, "elsewhere")
        os.makedirs(os.path.join(elsewhere, "JPC_AV_00033"))
        with open(os.path.join(elsewhere, "JPC_AV_00033", "JPC_AV_00033.mkv"), "wb") as f:
            f.write(b"placeholder")
        os.makedirs(os.path.join(self.tmp, "real34"))
        with open(os.path.join(self.tmp, "real34", "JPC_AV_00034.mkv"), "wb") as f:
            f.write(b"placeholder")
        os.symlink(elsewhere, os.path.join(self.server, "linked"))
        os.symlink(os.path.join(self.tmp, "real34"), os.path.join(self.server, "JPC_AV_00034"))
        run = self.run_script(self.write_csv([self.row("JPC_AV_00033"), self.row("JPC_AV_00034")]),
                              "--verify-uniqueness")
        self.assertEqual(run.code, 1, run.text)
        self.assertEqual(set(self.filenames(run).values()), {""})
        self.assertIn(f"{self.server}/JPC_AV_00034 is a symlinked folder; not followed", run.out)
        for path in run.logged("list"):
            self.assertFalse(path.startswith(os.path.join(self.server, "linked")), path)
            self.assertFalse(path.startswith(elsewhere), path)

    def test_symlinked_mkv_is_ignored_and_noted(self):
        target = os.path.join(self.tmp, "target.mkv")
        with open(target, "wb") as f:
            f.write(b"placeholder")
        folder = self.folder(date_dir("2024-09-20") + "/JPC_AV_00035")
        os.symlink(target, os.path.join(folder, "JPC_AV_00035.mkv"))
        run = self.run_script(self.write_csv([self.row("JPC_AV_00035", "2024-09-20")]))
        self.assertEqual(run.code, 1, run.text)
        self.assertIn("JPC_AV_00035.mkv is not a regular file (a symlink or other); ignored", run.out)


class EarlyStopTests(Base):

    def test_no_pass_2_when_every_row_is_found_in_its_date_folder(self):
        self.mkv(date_dir("2024-09-20") + "/JPC_AV_00040/JPC_AV_00040.mkv")
        deep = self.folder("zz/1/2/3/4")        # level 4 and below: only pass 2 lists them
        run = self.run_script(self.write_csv([self.row("JPC_AV_00040", "2024-09-20")]))
        self.assertEqual(run.code, 0, run.text)
        listed = run.logged("list")
        self.assertIn(os.path.join(self.server, "zz/1/2"), listed)    # pass 1 reached level 3
        self.assertNotIn(os.path.dirname(deep), listed)
        self.assertNotIn(deep, listed)

    def test_pass_2_stops_after_the_last_needed_match(self):
        self.mkv("aaa/JPC_AV_00041/JPC_AV_00041.mkv")
        self.mkv("bbb/JPC_AV_00042/JPC_AV_00042.mkv")
        self.folder("ccc/sub")
        self.folder("ddd")
        run = self.run_script(self.write_csv([self.row("JPC_AV_00041"), self.row("JPC_AV_00042")]))
        self.assertEqual(run.code, 0, run.text)
        listed = run.logged("list")
        self.assertIn(os.path.join(self.server, "bbb"), listed)
        for name in ("ccc", "ccc/sub", "ddd"):
            self.assertNotIn(os.path.join(self.server, name), listed)


class ScanErrorTests(Base):

    def setUp(self):
        super().setUp()
        self.found = self.mkv(date_dir("2024-09-20") + "/JPC_AV_00050/JPC_AV_00050.mkv")
        self.broken = self.folder("broken")
        self.rows = [self.row("JPC_AV_00050", "2024-09-20"), self.row("JPC_AV_00051", "2024-09-20")]

    def check_default_mode_warns_and_saves(self, kind):
        run = self.run_script(self.write_csv(self.rows), faults={kind: [self.broken]})
        self.assertTrue(run.fired(kind), run.text)
        self.assertEqual(run.code, 1, run.text)
        self.assertIn("Warning: 1 folder or entry could not be read:", run.out)
        self.assertIn(self.broken, run.out)
        self.assertIn("1 folder could not be read; it may be in one of them", run.out)
        self.assertEqual(self.filenames(run), {"JPC_AV_00050": self.found, "JPC_AV_00051": ""})

    def test_classification_error_is_reported_not_taken_as_a_file(self):
        self.check_default_mode_warns_and_saves("classify")

    def test_listing_error_is_reported(self):
        self.check_default_mode_warns_and_saves("list")

    def test_lstat_error_on_the_mkv_is_not_taken_as_absent(self):
        mkv = self.mkv("x/JPC_AV_00052/JPC_AV_00052.mkv")
        run = self.run_script(self.write_csv([self.row("JPC_AV_00052")]), faults={"lstat": [mkv]})
        self.assertTrue(run.fired("lstat"), run.text)
        self.assertEqual(run.code, 1, run.text)
        self.assertIn(f"{mkv} - Input/output error (injected)", run.out)
        self.assertNotIn("has no JPC_AV_00052.mkv", run.out)

    def test_verify_mode_with_an_error_saves_nothing(self):
        self.mkv("aaa/JPC_AV_00053/JPC_AV_00053.mkv")
        inner = self.folder("zzz/inner")      # classified only after aaa's match
        run = self.run_script(self.write_csv([self.row("JPC_AV_00053")]), "--verify-uniqueness",
                              faults={"classify": [inner]})
        self.assertTrue(run.fired("classify"), run.text)
        self.assertEqual(run.code, 1, run.text)
        self.assertIn("NOT saved: 1 folder or entry could not be read, so duplicate copies can't be ruled out",
                      run.out)
        self.assertEqual(run.outputs, [])


class DuplicateCopyTests(Base):

    def test_verify_mode_finds_a_second_copy_outside_the_date_folder(self):
        first = self.mkv(date_dir("2024-09-20") + "/JPC_AV_00070/JPC_AV_00070.mkv")
        second = self.mkv("other/JPC_AV_00070/JPC_AV_00070.mkv")
        run = self.run_script(self.write_csv([self.row("JPC_AV_00070", "2024-09-20")]),
                              "--verify-uniqueness")
        self.assertEqual(run.code, 1, run.text)
        self.assertIn("STOP: 1 row needs a person before this CSV goes to mkvnote", run.out)
        self.assertIn("found 2 copies on the server", run.out)
        self.assertIn(first, run.out)
        self.assertIn(second, run.out)
        self.assertEqual(self.filenames(run), {"JPC_AV_00070": ""})

        self.clear_outputs()
        run = self.run_script(self.write_csv([self.row("JPC_AV_00070", "2024-09-20")]))
        self.assertEqual(run.code, 0, run.text)     # by default one copy is assumed

    def test_two_copies_in_one_date_folder_stop_by_default(self):
        day = date_dir("2024-09-20")
        self.mkv(day + "/JPC_AV_00071/JPC_AV_00071.mkv")
        self.mkv(day + "/JPC_AV_00071_refid_x/JPC_AV_00071.mkv")
        run = self.run_script(self.write_csv([self.row("JPC_AV_00071", "2024-09-20")]))
        self.assertEqual(run.code, 1, run.text)
        self.assertIn("STOP: 1 row needs a person", run.out)
        self.assertEqual(self.filenames(run), {"JPC_AV_00071": ""})
        lines = run.out.rstrip().splitlines()
        self.assertIn("JPC_AV_00071_refid_x", lines[-1], "the banner's rows come last")


class PrefilledTests(Base):

    def test_matching_prefilled_path_is_confirmed_and_cleaned(self):
        path = self.mkv(date_dir("2024-09-20") + "/JPC_AV_00080/JPC_AV_00080.mkv")
        run = self.run_script(self.write_csv([self.row("JPC_AV_00080", "2024-09-20", filename=path + " ")]))
        self.assertEqual(run.code, 0, run.text)
        self.assertIn("already filled, confirmed:  1", run.out)
        self.assertEqual(self.filenames(run), {"JPC_AV_00080": path})

    def test_different_prefilled_path_is_kept_under_a_stop_banner(self):
        found = self.mkv(date_dir("2024-09-20") + "/JPC_AV_00081/JPC_AV_00081.mkv")
        wrong = "/Volumes/JPCARCHIVE/somewhere/else/JPC_AV_00081.mkv"
        run = self.run_script(self.write_csv([self.row("JPC_AV_00081", "2024-09-20", filename=wrong)]))
        self.assertEqual(run.code, 1, run.text)
        self.assertIn("STOP: 1 row needs a person", run.out)
        self.assertIn(f"in the CSV:  {wrong}", run.out)
        self.assertIn(f"found:       {found}", run.out)
        self.assertEqual(self.filenames(run), {"JPC_AV_00081": wrong})

    def test_prefilled_rows_with_an_unsafe_found_path(self):
        equal = self.mkv("Bob's/JPC_AV_00082/JPC_AV_00082.mkv")
        self.mkv("Bob's/JPC_AV_00083/JPC_AV_00083.mkv")
        rows = [self.row("JPC_AV_00082", filename=equal), self.row("JPC_AV_00083", filename="/elsewhere.mkv")]
        run = self.run_script(self.write_csv(rows))
        self.assertEqual(run.code, 1, run.text)
        self.assertRegex(run.out, r"JPC_AV_00082 +mkvnote can't use this path")
        self.assertIn("STOP: 1 row needs a person", run.out)
        self.assertIn("in the CSV:  /elsewhere.mkv", run.out)
        self.assertEqual(self.filenames(run), {"JPC_AV_00082": equal, "JPC_AV_00083": "/elsewhere.mkv"})


class CatalogRowTests(Base):

    def test_missing_malformed_and_repeated_catalog_numbers(self):
        self.mkv("x/JPC_AV_00090/JPC_AV_00090.mkv")
        rows = [self.row(""), self.row("JPC_AV_12"), self.row("JPC_AV_00090"), self.row("JPC_AV_00090")]
        run = self.run_script(self.write_csv(rows))
        self.assertEqual(run.code, 1, run.text)
        self.assertIn("no CATALOG_NUMBER", run.out)
        self.assertIn("'JPC_AV_12' is not a catalog number", run.out)
        self.assertIn("the same catalog number is also on line(s) 5", run.out)
        self.assertIn("the same catalog number is also on line(s) 4", run.out)
        self.assertEqual(run.logged("list"), [self.server], "only the root check; nothing searched")
        _, out_rows = self.read_output(self.only_output(run))
        self.assertEqual([r[0] for r in out_rows[1:]], ["", "", "", ""])


class CsvProblemTests(Base):

    def assert_refused(self, content, message):
        run = self.run_script(self.write_raw(content))
        self.assertEqual(run.code, 2, run.text)
        self.assertIn(message, run.err)
        self.assertIn("Nothing was written.", run.err)
        self.assertEqual(run.outputs, [])
        self.assertEqual(run.logged("list"), [], "the server is not touched")

    def test_header_problems(self):
        cases = [
            ("CATALOG_NUMBER,TITLE\nJPC_AV_00001,T\n", "the CSV has no 'filename' column"),
            ("filename,TITLE\n,T\n", "the CSV has no 'CATALOG_NUMBER' column"),
            ("filename,CATALOG_NUMBER,TITLE,TITLE\n,JPC_AV_00001,T,U\n", "the header repeats column name(s): 'TITLE'"),
            ("filename,file_name,CATALOG_NUMBER\n,,JPC_AV_00001\n", "mkvnote would read 'file_name'"),
            ("filename,_filename,CATALOG_NUMBER\n,,JPC_AV_00001\n", "mkvnote would read '_filename'"),
            ("filename,file name,CATALOG_NUMBER\n,,JPC_AV_00001\n", "mkvnote would read 'file name'"),
        ]
        for content, message in cases:
            with self.subTest(message=message):
                self.assert_refused(content, message)

    def test_unreadable_rows(self):
        cases = [
            ("filename,CATALOG_NUMBER,TITLE\n,JPC_AV_00001,T\n,JPC_AV_00002\n",
             "line 3: the row has 2 cells but the header has 3"),
            ('filename,CATALOG_NUMBER\n,"JPC_AV_00001"x\n', "the CSV can't be read at line 2"),
            (b"filename,CATALOG_NUMBER\n,JPC_AV_\xff\n", "is not UTF-8 text"),
            ("", "the CSV is empty"),
            (BOM + "filename,CATALOG_NUMBER\n", "No rows to process"),
            (BOM + "filename,CATALOG_NUMBER\n,\n , \n\n", "No rows to process"),
        ]
        for content, message in cases:
            with self.subTest(message=message):
                self.assert_refused(content, message)

    def test_an_empty_line_among_the_rows_is_dropped(self):
        self.mkv("x/JPC_AV_00100/JPC_AV_00100.mkv")
        self.mkv("x/JPC_AV_00101/JPC_AV_00101.mkv")
        run = self.run_script(self.write_raw("filename,CATALOG_NUMBER,TITLE\n,JPC_AV_00100,T\n\n,JPC_AV_00101,T\n"))
        self.assertEqual(run.code, 0, run.text)
        self.assertIn("(1 blank row dropped)", run.out)


class OutputTests(Base):

    def setUp(self):
        super().setUp()
        self.path = self.mkv(date_dir("2024-09-20") + "/JPC_AV_00060/JPC_AV_00060.mkv")
        self.csv = self.write_csv([self.row("JPC_AV_00060", "2024-09-20")])

    def test_o_puts_the_standard_name_in_that_folder(self):
        elsewhere = os.path.join(self.tmp, "out")
        os.makedirs(elsewhere)
        run = self.run_script(self.csv, "-o", elsewhere)
        self.assertEqual(run.code, 0, run.text)
        self.assertEqual(run.outputs, [])
        out = self.only_output(run, elsewhere)
        self.assertTrue(NAME_RE.match(os.path.basename(out)))

    def test_o_must_be_an_existing_folder(self):
        for target, message in ((os.path.join(self.tmp, "missing"), "-o folder not found"),
                                (self.csv, "-o must be a folder")):
            with self.subTest(target=target):
                run = self.run_script(self.csv, "-o", target)
                self.assertEqual(run.code, 2, run.text)
                self.assertIn(message, run.err)
                self.assertEqual(run.outputs, [])

    def test_an_existing_output_is_never_overwritten(self):
        now = datetime.now()
        taken = []
        for offset in range(-2, 30):
            stamp = (now + timedelta(seconds=offset)).strftime("%Y%m%d_%H%M%S")
            taken.append(self.write_raw(b"keep", f"batch_mkvnote-paths_{stamp}.csv"))
        run = self.run_script(self.csv)
        self.assertEqual(run.code, 2, run.text)
        self.assertIn("already exists (it was not touched)", run.out)
        self.assertIn("NOT saved:", run.out)
        self.assertEqual(len(run.outputs), len(taken))
        for path in taken:
            with open(path, "rb") as f:
                self.assertEqual(f.read(), b"keep")

    def test_a_failed_write_or_close_deletes_the_new_file(self):
        for kind, message in (("write", "No space left on device (injected)"),
                              ("close", "Input/output error (injected)")):
            with self.subTest(kind=kind):
                run = self.run_script(self.csv, faults={kind: True})
                self.assertTrue(run.fired(kind), run.text)
                self.assertEqual(run.code, 2, run.text)
                self.assertIn(f"NOT saved: writing", run.out)
                self.assertIn(message, run.out)
                self.assertNotIn("Saved:", run.out)
                self.assertEqual(run.outputs, [])

    def test_a_leftover_that_cannot_be_deleted_is_named(self):
        run = self.run_script(self.csv, faults={"write": True, "unlink": True})
        self.assertTrue(run.fired("write") and run.fired("unlink"), run.text)
        self.assertEqual(run.code, 2, run.text)
        self.assertEqual(len(run.outputs), 1)
        self.assertIn(f"A partial file was left at {os.path.join(self.work, run.outputs[0])}", run.out)


class RootTests(Base):

    def test_root_must_be_a_reachable_folder(self):
        csv_path = self.write_csv([self.row("JPC_AV_00001")])
        a_file = self.write_raw("x", "not-a-folder")
        cases = [(os.path.join(self.tmp, "missing"), "not found - is JPCARCHIVE mounted?"),
                 (a_file, "is not a folder")]
        for root, message in cases:
            with self.subTest(root=root):
                run = self.run_script(csv_path, "--root", root, root=False)
                self.assertEqual(run.code, 2, run.text)
                self.assertIn(message, run.err)
                self.assertEqual(run.outputs, [])
        self.lock(self.server)
        run = self.run_script(csv_path)
        self.assertEqual(run.code, 2, run.text)
        self.assertIn(f"can't list {self.server}", run.err)
        self.assertEqual(run.outputs, [])


class UnsafePathTests(Base):

    def test_a_path_with_an_apostrophe_is_not_written(self):
        self.mkv("Bob's tapes/JPC_AV_00110/JPC_AV_00110.mkv")
        run = self.run_script(self.write_csv([self.row("JPC_AV_00110")]))
        self.assertEqual(run.code, 1, run.text)
        self.assertRegex(run.out, r"JPC_AV_00110 +mkvnote can't use this path")
        self.assertEqual(self.filenames(run), {"JPC_AV_00110": ""})


class DefaultsTests(Base):

    OPTION_LINES = [r"CSV +The CSV exported", r"--root DIR +Search DIR instead of /Volumes/JPCARCHIVE/",
                    r"-o FOLDER +Save the new CSV", r"--verify-uniqueness +Flag files found twice"]

    def test_help(self):
        run = self.run_script("--help", root=False)
        self.assertEqual(run.code, 0, run.text)
        headings = [line for line in run.out.splitlines() if line and line == line.lstrip()
                    and line.isupper() and not line.startswith("=")]
        self.assertEqual(headings, ["DESCRIPTION", "USAGE", "ARGUMENTS", "OPTIONS",
                                    "HOW FILES ARE FOUND", "EXAMPLES", "OUTPUT", "EXIT"])
        for pattern in self.OPTION_LINES + [r"\n    130 interrupted", r"_mkvnote-paths_<yyyymmdd_hhmmss>\.csv"]:
            self.assertRegex(run.out, pattern)
        self.assertNotIn("\x1b[", run.out)              # no colors when not a terminal

    def test_argument_error_shows_usage_and_options(self):
        run = self.run_script(root=False)
        self.assertEqual(run.code, 2, run.text)
        self.assertEqual(run.out, "")
        self.assertTrue(run.err.startswith("\nusage: mkvnote_paths.py CSV [options]\n"
                                           "       Use -h or --help for detailed information\n"),
                        run.text)
        for pattern in self.OPTION_LINES:
            self.assertRegex(run.err, r"\n  " + pattern)
        self.assertTrue(run.err.endswith("\nerror: the following arguments are required: CSV\n"),
                        run.text)
        self.assertEqual(run.log, [])                   # stopped before reading anything

    def test_default_root_is_jpcarchive(self):
        run = self.run_script(self.write_csv([self.row("JPC_AV_00001")]), root=False)
        self.assertEqual(run.code, 99, run.text)        # the wrapper's guard stopped it
        self.assertEqual(run.logged("BLOCKED"), ["/Volumes/JPCARCHIVE"])
        self.assertEqual(run.outputs, [])


class InterruptTests(Base):

    def test_ctrl_c_during_the_search_saves_nothing(self):
        aaa = self.folder("aaa")
        self.mkv("bbb/JPC_AV_00120/JPC_AV_00120.mkv")
        csv_path = self.write_csv([self.row("JPC_AV_00120")])
        env = {"PATH": "/usr/bin:/bin", "HOME": self.home, "TMPDIR": self.temp, "LANG": "en_US.UTF-8",
               "MP_LOG": self.logfile, "MP_FAULTS": json.dumps({"pause": [aaa]})}
        proc = subprocess.Popen([sys.executable, self.wrapper, SCRIPT, csv_path, "--root", self.server],
                                env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.time() + 20
            while time.time() < deadline and ["PAUSED", aaa] not in self.read_log():
                time.sleep(0.05)
            self.assertIn(["PAUSED", aaa], self.read_log(), "the search never reached the pause")
            proc.send_signal(signal.SIGINT)
            out, err = proc.communicate(timeout=20)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()
        self.assertEqual(proc.returncode, 130, out + err)
        self.assertIn("Interrupted (Ctrl-C). Nothing was saved.", err)
        self.assertEqual(self.outputs(), [])


if __name__ == "__main__":
    unittest.main()

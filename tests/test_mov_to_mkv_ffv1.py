#!/usr/bin/env python3
"""Focused tests for mov_to_mkv_ffv1.py - standard library only.

Every case runs the script itself, as a separate process, on synthetic
placeholder .mov files in a temporary folder, with a fake `ffmpeg` first on
PATH (the real one is kept off PATH). The fake records each call and writes
small placeholder outputs; it can also fail, or keep running until it is
stopped. Nothing here encodes media, so these tests say nothing about media
fidelity, FFmpeg compatibility or preservation-policy compliance.

    python3 tests/test_mov_to_mkv_ffv1.py          # from the repository folder

MOV_TO_MKV_SCRIPT=/path/to/other/version.py runs the same checks against
another copy of the script (to show what an older version did).
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get("MOV_TO_MKV_SCRIPT",
                        os.path.join(os.path.dirname(HERE), "mov_to_mkv_ffv1.py"))

FAKE_FFMPEG = r'''#!{python}
import json, os, signal, sys, time
args = sys.argv[1:]
with open(os.environ["FAKE_FFMPEG_CALLS"], "a") as f:
    f.write(json.dumps(args) + "\n")
with open(os.environ["FAKE_FFMPEG_CONFIG"]) as f:
    config = json.load(f)
if args == ["-version"]:
    print("ffmpeg version %s Copyright (c) synthetic test stand-in" % config.get("version", "7.1"))
    sys.exit(0)
if config.get("read_stdin"):                  # as ffmpeg reads keys: [q] stops it early
    keys = sys.stdin.read()
    with open(os.environ["FAKE_FFMPEG_PID"] + ".stdin", "w") as f:
        f.write(keys)
    if "q" in keys:
        with open(args[-1], "wb") as f:
            f.write(b"TRUNCATED by q")
        sys.exit(0)
out = args[-1]
kind = "access" if out.endswith("_access.mp4") else "mkv"
mode = config.get(kind, "ok")                 # ok | fail | hang
if any(name in out for name in config.get("fail_for", [])):
    mode = "fail"
if "-n" in args and os.path.lexists(out):
    sys.stderr.write("File '%s' already exists. Exiting.\n" % out)
    sys.exit(1)
if mode == "fail":
    sys.stderr.write("synthetic encoder failure\n")
    sys.exit(1)
if mode == "hang":                            # runs until stopped (20 s at most)
    def stopped(signum, frame):              # finishes up for a moment, as ffmpeg does
        with open(os.environ["FAKE_FFMPEG_PID"] + ".term", "w") as f:
            f.write("SIGTERM")
        time.sleep(1.0)
        sys.exit(255)
    signal.signal(signal.SIGTERM, stopped)
    with open(out, "wb") as f:
        f.write(b"partial")
    with open(os.environ["FAKE_FFMPEG_PID"], "w") as f:
        f.write(str(os.getpid()))
    for n in range(200):
        try:
            sys.stderr.write("frame=%d synthetic progress\n" % n)
            sys.stderr.flush()
        except OSError:
            pass
        time.sleep(0.1)
    sys.exit(0)
for n in range(3):
    sys.stderr.write("frame=%d synthetic progress\n" % n)
with open(out, "wb") as f:
    f.write(b"synthetic " + kind.encode())
sys.exit(0)
'''

UTC_STAMP = re.compile(r"creation_time=\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.000000Z$")


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class ConverterTest(unittest.TestCase):

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="mov_to_mkv_test_"))
        self.bin = os.path.join(self.tmp, "bin")
        self.src = os.path.join(self.tmp, "batch")
        os.makedirs(self.bin)
        os.makedirs(self.src)
        fake = os.path.join(self.bin, "ffmpeg")
        with open(fake, "w") as f:
            f.write(FAKE_FFMPEG.replace("{python}", sys.executable))
        os.chmod(fake, 0o755)
        self.calls = os.path.join(self.tmp, "calls.jsonl")
        self.config_path = os.path.join(self.tmp, "config.json")
        self.pid_file = os.path.join(self.tmp, "ffmpeg.pid")
        self.configure()
        self.env = {
            "PATH": os.pathsep.join([self.bin, "/usr/bin", "/bin"]),
            "HOME": self.tmp,
            "LANG": "en_US.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "FAKE_FFMPEG_CALLS": self.calls,
            "FAKE_FFMPEG_CONFIG": self.config_path,
            "FAKE_FFMPEG_PID": self.pid_file,
        }
        found = shutil.which("ffmpeg", path=self.env["PATH"])
        self.assertEqual(found, fake, "only the fake ffmpeg may be reachable")
        self.assertIsNone(shutil.which("ffmpeg", path="/usr/bin:/bin"),
                          "a real ffmpeg in /usr/bin or /bin: these tests would reach it")
        self.children = []

    def tearDown(self):
        for pid in self.children:              # an older version can leave one running
            if alive(pid):
                os.kill(pid, signal.SIGKILL)
        os.chmod(self.src, 0o755)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers -----------------------------------------------------------
    def configure(self, **modes):
        with open(self.config_path, "w") as f:
            json.dump(modes, f)

    def mov(self, name="JPC_AV_00001.mov"):
        path = os.path.join(self.src, name)
        with open(path, "wb") as f:
            f.write(b"synthetic placeholder, not media")
        return path

    def existing(self, base, *suffixes):
        """Pre-existing outputs for <base>, each with distinct content."""
        folder = os.path.join(self.src, base)
        os.makedirs(folder, exist_ok=True)
        for suffix in suffixes:
            with open(os.path.join(folder, base + suffix), "w") as f:
                f.write("PRE-EXISTING " + suffix)

    def read(self, base, suffix):
        with open(os.path.join(self.src, base, base + suffix)) as f:
            return f.read()

    def ffmpeg_calls(self, encodes_only=True):
        if not os.path.exists(self.calls):
            return []
        with open(self.calls) as f:
            calls = [json.loads(line) for line in f]
        return [c for c in calls if c != ["-version"]] if encodes_only else calls

    def run_script(self, *args, keys=None):
        r = subprocess.run([sys.executable, SCRIPT, *args, "--no-color"], env=self.env,
                           stdin=subprocess.DEVNULL if keys is None else None,
                           input=keys, capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout, r.stderr

    def start_script(self, *args, stderr, stdout=None, preexec_fn=None):
        out = open(os.path.join(self.tmp, "stdout.txt"), "w")
        p = subprocess.Popen([sys.executable, SCRIPT, *args, "--no-color"], env=self.env,
                             stdin=subprocess.DEVNULL, stdout=stdout or out, stderr=stderr,
                             preexec_fn=preexec_fn)
        out.close()
        return p

    def wait_for_encoder(self):
        deadline = time.time() + 15
        while time.time() < deadline:
            if os.path.exists(self.pid_file):
                with open(self.pid_file) as f:
                    text = f.read()
                if text:
                    pid = int(text)
                    self.children.append(pid)
                    return pid
            time.sleep(0.05)
        self.fail("the fake ffmpeg never started")

    def assert_reaped(self, pid):
        """Stopped and waited for by the script itself: the encoder no longer
        exists the moment the script has exited (it takes a second to finish
        after SIGTERM, so a script that does not wait for it fails this)."""
        self.assertFalse(alive(pid), "the encoder outlived the script")
        self.assertTrue(os.path.exists(self.pid_file + ".term"), "the encoder was not stopped")

    def stdout_file(self):
        with open(os.path.join(self.tmp, "stdout.txt")) as f:
            return f.read()

    def snapshot(self):
        """Every path and file content under the batch folder."""
        state = {}
        for root, dirs, files in os.walk(self.src):
            for d in dirs:
                state[os.path.relpath(os.path.join(root, d), self.src)] = "<dir>"
            for name in files:
                path = os.path.join(root, name)
                with open(path, "rb") as f:
                    state[os.path.relpath(path, self.src)] = f.read()
        return state

    @staticmethod
    def count(out, label):
        m = re.search(r"^\s*" + re.escape(label) + r"\s+(\d+)", out, re.M)
        return int(m.group(1)) if m else 0

    # -- the four recorded review observations -----------------------------
    def test_an_existing_log_alone_is_kept_and_its_file_skipped(self):
        """Observation 1: a default run never replaces an existing log."""
        self.mov()
        self.existing("JPC_AV_00001", "_conversion.log")
        code, out, err = self.run_script("-d", self.src)
        self.assertEqual(self.read("JPC_AV_00001", "_conversion.log"),
                         "PRE-EXISTING _conversion.log")
        self.assertEqual(self.ffmpeg_calls(), [])
        self.assertIn("Skipped: already exists: JPC_AV_00001_conversion.log", out)
        self.assertEqual((code, self.count(out, "Skipped:"), self.count(out, "Converted:")),
                         (0, 1, 0), out + err)

    def test_a_dry_run_with_overwrite_counts_an_existing_mkv_as_converted(self):
        """Observation 2: a dry run honours --overwrite like a real run."""
        self.mov()
        self.existing("JPC_AV_00001", ".mkv")
        before = self.snapshot()
        code, out, err = self.run_script("-d", self.src, "--dry-run", "--overwrite")
        self.assertEqual((self.count(out, "Would convert:"), self.count(out, "Would skip:")),
                         (1, 0), out)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.ffmpeg_calls(encodes_only=False), [])
        self.assertIn("Would replace JPC_AV_00001.mkv", out)
        self.assertEqual(code, 0, err)

    def test_a_failed_conversion_exits_nonzero(self):
        """Observation 3: a failed conversion is a nonzero command exit."""
        self.mov()
        self.configure(mkv="fail")
        code, out, err = self.run_script("-d", self.src)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(self.count(out, "Failed:"), 1, out)
        self.assertNotIn("FFV1/MKV complete", out)
        log = self.read("JPC_AV_00001", "_conversion.log")
        self.assertIn("Status:       FAILED", log)
        self.assertNotIn("Result: SUCCESS", log)

    def test_ctrl_c_during_progress_stops_and_reaps_the_encoder(self):
        """Observation 4: an interrupted --progress run leaves no encoder
        running (only the script gets the SIGINT here, not the encoder)."""
        self.mov()
        self.mov("JPC_AV_00002.mov")
        self.configure(mkv="hang")
        with open(os.path.join(self.tmp, "stderr.txt"), "w") as err:
            p = self.start_script("-d", self.src, "--progress", stderr=err)
            child = self.wait_for_encoder()
            time.sleep(0.4)                     # progress is flowing
            os.kill(p.pid, signal.SIGINT)
            code = p.wait(timeout=30)
        self.assert_reaped(child)
        self.assertEqual(code, 130)
        out = self.stdout_file()
        self.assertIn("Interrupted (Ctrl-C) during the FFV1/MKV step", out)
        self.assertNotIn("FFV1/MKV complete", out)
        self.assertEqual(self.count(out, "Not started:"), 1, out)
        log = self.read("JPC_AV_00001", "_conversion.log")
        self.assertIn("Status:       INTERRUPTED", log)
        self.assertNotIn("Result: SUCCESS", log)
        self.assertEqual(self.read("JPC_AV_00001", ".mkv"), "partial")   # kept, not deleted
        self.assertFalse(os.path.exists(os.path.join(self.src, "JPC_AV_00002")))

    # -- interruption and output failure -----------------------------------
    def test_a_failed_progress_output_stops_and_reaps_the_encoder(self):
        self.mov()
        self.configure(mkv="hang")
        p = self.start_script("-d", self.src, "--progress", stderr=subprocess.PIPE)
        child = self.wait_for_encoder()
        p.stderr.readline()                     # the progress relay is running
        p.stderr.close()                        # ... and now its reader is gone
        code = p.wait(timeout=30)
        self.assert_reaped(child)
        self.assertEqual(code, 1)
        out = self.stdout_file()
        self.assertIn("The progress output failed", out)
        self.assertNotIn("FFV1/MKV complete", out)
        log = self.read("JPC_AV_00001", "_conversion.log")
        self.assertIn("Status:       FAILED", log)
        self.assertIn("progress output failed", log)

    def test_ctrl_c_without_progress_stops_the_encoder_and_says_so(self):
        self.mov()
        self.configure(mkv="hang")
        with open(os.path.join(self.tmp, "stderr.txt"), "w") as err:
            p = self.start_script("-d", self.src, stderr=err)
            child = self.wait_for_encoder()
            time.sleep(0.4)
            os.kill(p.pid, signal.SIGINT)
            code = p.wait(timeout=30)
        self.assert_reaped(child)
        self.assertEqual(code, 130)
        log = self.read("JPC_AV_00001", "_conversion.log")
        self.assertIn("Status:       INTERRUPTED", log)
        self.assertIn("frame=", log)                     # ffmpeg's output is kept in the log
        self.assertEqual(self.count(self.stdout_file(), "Interrupted:"), 1)

    # -- normal success and the retained encoding settings -----------------
    def test_a_normal_run_converts_mov_and_MOV_with_the_committed_settings(self):
        first, second = self.mov("JPC_AV_00001.mov"), self.mov("JPC_AV_00002.MOV")
        code, out, err = self.run_script("-d", self.src)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.count(out, "Converted:"), 2, out)
        for base in ("JPC_AV_00001", "JPC_AV_00002"):
            self.assertEqual(self.read(base, ".mkv"), "synthetic mkv")
            self.assertEqual(self.read(base, "_access.mp4"), "synthetic access")
            self.assertIn("Status:       SUCCESS", self.read(base, "_conversion.log"))
        self.assertTrue(os.path.exists(first) and os.path.exists(second))   # sources kept
        calls = self.ffmpeg_calls()
        self.assertEqual(len(calls), 4, calls)
        mkv, access = calls[0], calls[1]
        stamp = mkv[mkv.index("-metadata") + 1]
        self.assertRegex(stamp, UTC_STAMP)
        out_mkv = os.path.join(self.src, "JPC_AV_00001", "JPC_AV_00001.mkv")
        self.assertEqual(mkv, [
            "-apply_cropping", "0", "-i", first, "-map", "0:v", "-map", "0:a",
            "-c:v", "ffv1", "-level", "3", "-coder", "1", "-context", "1", "-g", "1",
            "-slicecrc", "1", "-slices", "24", "-vf", "setfield=bff", "-top", "0",
            "-flags", "+ilme+ildct", "-vtag", "FFV1", "-metadata", stamp,
            "-c:a", "flac", "-f", "matroska", "-n", out_mkv])
        self.assertEqual(access, [
            "-apply_cropping", "0", "-i", first, "-map", "0:v", "-map", "0:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "28", "-c:a", "aac",
            "-b:a", "128k", "-movflags", "+faststart", "-n",
            os.path.join(self.src, "JPC_AV_00001", "JPC_AV_00001_access.mp4")])

    # -- skips and overwrite modes -----------------------------------------
    def test_an_existing_mkv_skips_its_file_and_skips_are_not_failures(self):
        self.mov()
        self.mov("JPC_AV_00002.mov")
        self.existing("JPC_AV_00001", ".mkv")
        before = self.snapshot()["JPC_AV_00001/JPC_AV_00001.mkv"]
        code, out, err = self.run_script("-d", self.src)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((self.count(out, "Converted:"), self.count(out, "Skipped:"),
                          self.count(out, "Failed:")), (1, 1, 0), out)
        self.assertEqual(self.snapshot()["JPC_AV_00001/JPC_AV_00001.mkv"], before)
        self.assertNotIn("JPC_AV_00001_conversion.log", os.listdir(os.path.join(self.src, "JPC_AV_00001")))

    def test_an_existing_access_derivative_skips_its_file_by_default(self):
        self.mov()
        self.existing("JPC_AV_00001", "_access.mp4")
        code, out, err = self.run_script("-d", self.src)
        self.assertEqual((code, self.count(out, "Skipped:")), (0, 1), out + err)
        self.assertEqual(self.ffmpeg_calls(), [])
        self.assertEqual(self.read("JPC_AV_00001", "_access.mp4"), "PRE-EXISTING _access.mp4")

    def test_no_access_neither_checks_nor_touches_an_existing_access_derivative(self):
        self.mov()
        self.existing("JPC_AV_00001", "_access.mp4")
        code, out, err = self.run_script("-d", self.src, "--no-access")
        self.assertEqual((code, self.count(out, "Converted:")), (0, 1), out + err)
        self.assertEqual(self.read("JPC_AV_00001", "_access.mp4"), "PRE-EXISTING _access.mp4")
        self.assertEqual([c[-1].endswith(".mkv") for c in self.ffmpeg_calls()], [True])

    def test_overwrite_replaces_the_mkv_and_log_and_keeps_the_access_derivative(self):
        self.mov()
        self.existing("JPC_AV_00001", ".mkv", "_conversion.log", "_access.mp4")
        code, out, err = self.run_script("-d", self.src, "--overwrite")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.read("JPC_AV_00001", ".mkv"), "synthetic mkv")
        self.assertIn("Status:       SUCCESS", self.read("JPC_AV_00001", "_conversion.log"))
        self.assertEqual(self.read("JPC_AV_00001", "_access.mp4"), "PRE-EXISTING _access.mp4")
        calls = self.ffmpeg_calls()
        self.assertEqual(len(calls), 1, calls)          # the access derivative is not remade
        self.assertEqual(calls[0][-2], "-y")
        self.assertIn("Keeping the existing JPC_AV_00001_access.mp4", out)
        self.assertIn("Existing access derivative kept", self.read("JPC_AV_00001", "_conversion.log"))

    def test_overwrite_makes_a_missing_access_derivative_without_replacing(self):
        self.mov()
        self.existing("JPC_AV_00001", ".mkv")
        code, out, err = self.run_script("-d", self.src, "--overwrite")
        self.assertEqual(code, 0, out + err)
        flags = {os.path.basename(c[-1]): c[-2] for c in self.ffmpeg_calls()}
        self.assertEqual(flags, {"JPC_AV_00001.mkv": "-y", "JPC_AV_00001_access.mp4": "-n"})

    def test_overwrite_all_replaces_every_output(self):
        self.mov()
        self.existing("JPC_AV_00001", ".mkv", "_conversion.log", "_access.mp4")
        code, out, err = self.run_script("-d", self.src, "--overwrite-all")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.read("JPC_AV_00001", ".mkv"), "synthetic mkv")
        self.assertEqual(self.read("JPC_AV_00001", "_access.mp4"), "synthetic access")
        self.assertIn("Status:       SUCCESS", self.read("JPC_AV_00001", "_conversion.log"))
        self.assertEqual([c[-2] for c in self.ffmpeg_calls()], ["-y", "-y"])

    # -- dry-run parity ----------------------------------------------------
    def test_a_dry_run_matches_the_real_run_creates_nothing_and_runs_no_ffmpeg(self):
        cases = {"JPC_AV_00001": (), "JPC_AV_00002": (".mkv",),
                 "JPC_AV_00003": ("_conversion.log",), "JPC_AV_00004": ("_access.mp4",)}
        expected = {(): ({"JPC_AV_00002", "JPC_AV_00003", "JPC_AV_00004"}, 0),
                    ("--overwrite",): (set(), 1),
                    ("--overwrite-all",): (set(), 0),
                    ("--no-access",): ({"JPC_AV_00002", "JPC_AV_00003"}, 0)}
        for options, (skipped, kept) in expected.items():
            with self.subTest(options=options):
                shutil.rmtree(self.src)
                os.makedirs(self.src)
                if os.path.exists(self.calls):
                    os.remove(self.calls)
                for base, suffixes in cases.items():
                    self.mov(base + ".mov")
                    self.existing(base, *suffixes) if suffixes else None
                before = self.snapshot()
                code, dry, err = self.run_script("-d", self.src, "--dry-run", *options)
                self.assertEqual(code, 0, dry + err)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.ffmpeg_calls(encodes_only=False), [])
                code, real, err = self.run_script("-d", self.src, *options)
                self.assertEqual(code, 0, real + err)
                for out, verb in ((dry, "Would skip:"), (real, "Skipped:")):
                    files_part = out.split("\nSUMMARY")[0]
                    blocks = re.split(r"^\[\d+/\d+\] ", files_part, flags=re.M)[1:]
                    found = {b.split(".")[0] for b in blocks if verb in b}
                    self.assertEqual(found, skipped, out)
                self.assertEqual(self.count(dry, "Would convert:"), 4 - len(skipped))
                self.assertEqual(self.count(real, "Converted:"), 4 - len(skipped))
                self.assertEqual(self.count(dry, "Would skip:"), self.count(real, "Skipped:"))
                self.assertEqual(self.count(dry, "Would keep existing access derivatives:"), kept)
                self.assertEqual(self.count(real, "Existing access derivatives kept "
                                                  "(not remade or checked):"), kept)

    # -- failure exit statuses ---------------------------------------------
    def test_an_access_failure_exits_nonzero_and_keeps_the_good_mkv(self):
        self.mov()
        self.configure(access="fail")
        code, out, err = self.run_script("-d", self.src)
        self.assertEqual(code, 1, out + err)
        self.assertEqual((self.count(out, "Converted:"), self.count(out, "Failed:")), (0, 1), out)
        self.assertEqual(self.read("JPC_AV_00001", ".mkv"), "synthetic mkv")
        self.assertNotIn("H.264/MP4 access complete", out)
        self.assertIn("Status:       FAILED", self.read("JPC_AV_00001", "_conversion.log"))

    def test_one_failure_among_successes_and_skips_still_exits_nonzero(self):
        for n in (1, 2, 3, 4):
            self.mov(f"JPC_AV_0000{n}.mov")
        self.existing("JPC_AV_00004", ".mkv")
        self.configure(fail_for=["JPC_AV_00002.mkv"])
        code, out, err = self.run_script("-d", self.src)
        self.assertEqual(code, 1, out + err)
        self.assertEqual((self.count(out, "Converted:"), self.count(out, "Failed:"),
                          self.count(out, "Skipped:")), (2, 1, 1), out)
        self.assertIn("Status:       FAILED", self.read("JPC_AV_00002", "_conversion.log"))

    def test_missing_ffmpeg_exits_nonzero_before_creating_anything(self):
        self.mov()
        os.remove(os.path.join(self.bin, "ffmpeg"))
        before = self.snapshot()
        code, out, err = self.run_script("-d", self.src)
        self.assertEqual(code, 1, out + err)
        self.assertIn("ffmpeg not found", out)
        self.assertEqual(self.snapshot(), before)

    def test_single_refuses_a_folder_named_like_a_mov(self):
        os.makedirs(os.path.join(self.src, "JPC_AV_00001.mov"))
        code, out, err = self.run_script("--single", os.path.join(self.src, "JPC_AV_00001.mov"))
        self.assertEqual(code, 1, out + err)
        self.assertIn("Not a file", out)
        self.assertEqual(self.ffmpeg_calls(encodes_only=False), [])

    # -- review round two --------------------------------------------------
    def test_sigterm_stops_and_reaps_the_encoder_like_ctrl_c(self):
        self.mov()
        self.configure(mkv="hang")
        with open(os.path.join(self.tmp, "stderr.txt"), "w") as err:
            p = self.start_script("-d", self.src, "--progress", stderr=err)
            child = self.wait_for_encoder()
            time.sleep(0.4)
            os.kill(p.pid, signal.SIGTERM)
            code = p.wait(timeout=30)
        self.assert_reaped(child)
        self.assertEqual(code, 143)
        log = self.read("JPC_AV_00001", "_conversion.log")
        self.assertIn("Status:       INTERRUPTED", log)
        self.assertIn("interrupted (SIGTERM)", log)

    def test_keyboard_input_never_reaches_ffmpeg(self):
        """A [q] typed while ffmpeg runs would stop it early with status 0."""
        self.mov()
        self.configure(read_stdin=True)
        code, out, err = self.run_script("-d", self.src, "--no-access", keys="q\n")
        self.assertEqual(code, 0, out + err)
        with open(self.pid_file + ".stdin") as f:
            self.assertEqual(f.read(), "")
        self.assertEqual(self.read("JPC_AV_00001", ".mkv"), "synthetic mkv")

    def test_a_hard_kill_leaves_an_in_progress_log_not_an_old_success(self):
        self.mov()
        self.existing("JPC_AV_00001", ".mkv")
        with open(os.path.join(self.src, "JPC_AV_00001", "JPC_AV_00001_conversion.log"), "w") as f:
            f.write("old log\nStatus:       SUCCESS\n")
        self.configure(mkv="hang")
        with open(os.path.join(self.tmp, "stderr.txt"), "w") as err:
            p = self.start_script("-d", self.src, "--overwrite", "--no-access", stderr=err)
            self.wait_for_encoder()
            os.kill(p.pid, signal.SIGKILL)      # nothing can run after this
            p.wait(timeout=30)
        log = self.read("JPC_AV_00001", "_conversion.log")
        self.assertIn("Status:       IN PROGRESS", log)
        self.assertNotIn("SUCCESS", log)

    def test_inputs_sharing_an_output_folder_match_in_dry_and_real_runs(self):
        first = self.mov()
        for options in ((), ("--overwrite",)):
            with self.subTest(options=options):
                code, dry, err = self.run_script("--single", first, first, "--dry-run", *options)
                self.assertEqual((self.count(dry, "Would convert:"), self.count(dry, "Would skip:")),
                                 (1, 1), dry)
                code, real, err = self.run_script("--single", first, first, *options)
                self.assertEqual((self.count(real, "Converted:"), self.count(real, "Skipped:")),
                                 (1, 1), real)
                self.assertIn("is also the one for JPC_AV_00001.mov, earlier in this run", real)
                shutil.rmtree(os.path.join(self.src, "JPC_AV_00001"))

    def test_the_skip_message_for_an_access_file_names_overwrite_all(self):
        self.mov()
        self.existing("JPC_AV_00001", "_access.mp4")
        code, out, err = self.run_script("-d", self.src, "--dry-run")
        self.assertIn("--overwrite replaces the .mkv and log but keeps the access .mp4; "
                      "--overwrite-all replaces all", out)

    def test_a_symlinked_output_is_never_written_through(self):
        self.mov()
        os.makedirs(os.path.join(self.src, "JPC_AV_00001"))
        other = os.path.join(self.tmp, "unrelated.txt")
        with open(other, "w") as f:
            f.write("UNRELATED")
        os.symlink(other, os.path.join(self.src, "JPC_AV_00001", "JPC_AV_00001_conversion.log"))
        code, out, err = self.run_script("-d", self.src, "--overwrite-all")
        self.assertEqual((code, self.count(out, "Skipped:")), (0, 1), out + err)
        self.assertIn("a symbolic link", out)
        with open(other) as f:
            self.assertEqual(f.read(), "UNRELATED")
        self.assertEqual(self.ffmpeg_calls(), [])

    def test_an_older_ffmpeg_is_refused_before_anything_is_created(self):
        self.mov()
        self.configure(version="7.0")
        before = self.snapshot()
        code, out, err = self.run_script("-d", self.src)
        self.assertEqual(code, 1, out + err)
        self.assertIn("needs FFmpeg 7.1 or later", out)
        self.assertEqual((self.snapshot(), self.ffmpeg_calls()), (before, []))

    def test_an_unwritable_batch_folder_fails_cleanly_with_a_summary(self):
        self.mov()
        self.mov("JPC_AV_00002.mov")
        os.chmod(self.src, 0o555)
        code, out, err = self.run_script("-d", self.src)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(self.count(out, "Failed:"), 2, out)
        self.assertIn("SUMMARY", out)
        self.assertNotIn("Traceback", err)

    def test_a_closed_standard_output_starts_no_file_and_exits_1_not_120(self):
        self.mov()
        p = subprocess.Popen([sys.executable, SCRIPT, "-d", self.src, "--no-color"], env=self.env,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        p.stdout.close()                        # the reader has gone before any file
        err = p.stderr.read()
        p.stderr.close()
        self.assertEqual(p.wait(timeout=60), 1, err)
        self.assertNotIn("Traceback", err)
        self.assertFalse(os.path.exists(os.path.join(self.src, "JPC_AV_00001")))
        self.assertEqual(self.ffmpeg_calls(), [])

    def test_a_hang_up_after_the_terminal_has_gone_still_logs_and_exits_129(self):
        self.mov()
        self.configure(mkv="hang")
        with open(os.path.join(self.tmp, "stderr.txt"), "w") as err:
            p = self.start_script("-d", self.src, stderr=err, stdout=subprocess.PIPE)
            child = self.wait_for_encoder()
            p.stdout.close()                    # the terminal has gone ...
            os.kill(p.pid, signal.SIGHUP)       # ... and the hang-up arrives
            code = p.wait(timeout=30)
        self.assert_reaped(child)
        self.assertEqual(code, 129)
        log = self.read("JPC_AV_00001", "_conversion.log")
        self.assertIn("Status:       INTERRUPTED", log)
        self.assertIn("interrupted (SIGHUP)", log)
        with open(os.path.join(self.tmp, "stderr.txt")) as f:
            self.assertNotIn("Traceback", f.read())

    def test_a_run_under_nohup_keeps_ignoring_sighup(self):
        self.mov()
        self.configure(mkv="hang")
        with open(os.path.join(self.tmp, "stderr.txt"), "w") as err:
            p = self.start_script("-d", self.src, stderr=err,
                                  preexec_fn=lambda: signal.signal(signal.SIGHUP, signal.SIG_IGN))
            child = self.wait_for_encoder()
            os.kill(p.pid, signal.SIGHUP)
            time.sleep(0.5)
            self.assertIsNone(p.poll(), "the run stopped on SIGHUP under nohup")
            self.assertTrue(alive(child))
            os.kill(p.pid, signal.SIGINT)
            code = p.wait(timeout=30)
        self.assertEqual(code, 130)
        self.assert_reaped(child)

    def test_an_interrupted_access_step_names_overwrite_all(self):
        self.mov()
        self.configure(access="hang")
        with open(os.path.join(self.tmp, "stderr.txt"), "w") as err:
            p = self.start_script("-d", self.src, stderr=err)
            child = self.wait_for_encoder()
            os.kill(p.pid, signal.SIGINT)
            code = p.wait(timeout=30)
        self.assert_reaped(child)
        self.assertEqual(code, 130)
        self.assertIn("during the H.264/MP4 access step - its output is incomplete "
                      "(only --overwrite-all remakes it)", self.stdout_file())

    def test_a_symlinked_output_folder_is_never_written_through(self):
        self.mov()
        elsewhere = os.path.join(self.tmp, "elsewhere")
        os.makedirs(elsewhere)
        os.symlink(elsewhere, os.path.join(self.src, "JPC_AV_00001"))
        code, out, err = self.run_script("-d", self.src, "--overwrite-all")
        self.assertEqual((code, self.count(out, "Skipped:")), (0, 1), out + err)
        self.assertEqual(os.listdir(elsewhere), [])

    def test_a_second_ctrl_c_while_ffmpeg_stops_keeps_its_output_in_the_log(self):
        self.mov()
        self.configure(mkv="hang")
        with open(os.path.join(self.tmp, "stderr.txt"), "w") as err:
            p = self.start_script("-d", self.src, "--progress", stderr=err)
            child = self.wait_for_encoder()
            time.sleep(0.4)
            os.kill(p.pid, signal.SIGINT)
            deadline = time.time() + 10
            while not os.path.exists(self.pid_file + ".term") and time.time() < deadline:
                time.sleep(0.02)
            os.kill(p.pid, signal.SIGINT)       # again, while ffmpeg finishes up
            code = p.wait(timeout=30)
        self.assertFalse(alive(child), "the encoder outlived the script")
        self.assertEqual(code, 130)
        log = self.read("JPC_AV_00001", "_conversion.log")
        self.assertIn("Status:       INTERRUPTED", log)
        self.assertIn("frame=", log)

    def test_help_states_the_overwrite_rules_and_exit_statuses(self):
        code, out, err = self.run_script("--help")
        self.assertEqual(code, 0)
        for text in ("--overwrite-all", "EXISTING OUTPUTS", "EXIT STATUS", "130", "129",
                     "failed or was\n      interrupted",
                     "existing access file (not remade or checked)", "143",
                     "Before real use"):
            self.assertIn(text, out)
        flat = " ".join(out.split())            # the startup-interruption guidance, any wrapping
        for text in ("ffmpeg is still starting can escape that",
                     "identify this conversion's ffmpeg by its PID and full command, "
                     "including its source and output paths",
                     "stop only that process - leave unrelated capture or encoding jobs running",
                     "If you cannot identify it confidently, ask for help before stopping anything",
                     "Treat this conversion's outputs as incomplete before retrying"):
            self.assertIn(text, flat)


if __name__ == "__main__":
    unittest.main(verbosity=2)

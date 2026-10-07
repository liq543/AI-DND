"""Append-only, hash-chained, HMAC-signed event log — the campaign's mechanical memory.

Game state is never stored directly: it is rebuilt by replaying events.jsonl. Each event carries
the HMAC of (previous hash + its own content) under a per-campaign secret stored with the campaign
(campaigns/<name>/engine/signing.key) so the campaign travels between machines via git. Editing,
deleting, reordering or inserting any line breaks the chain, and the engine refuses to continue until
the tampering is resolved with `engine verify`. Older campaigns may still keep their key in
~/.dnd-engine/keys/; `engine rekey` moves them to a fresh in-repo key.
"""
import datetime
import hashlib
import hmac
import json
import os
import secrets
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAMPAIGNS = Path(os.environ.get("DND_CAMPAIGNS", ROOT / "campaigns"))
ACTIVE_FILE = CAMPAIGNS / "ACTIVE"
KEY_DIR = Path(os.environ.get("DND_ENGINE_HOME", Path.home() / ".dnd-engine")) / "keys"
GENESIS = "0" * 64


class TamperError(RuntimeError):
    pass


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Store:
    def __init__(self, campaign_dir):
        self.dir = Path(campaign_dir)
        self.engine_dir = self.dir / "engine"
        self.events_path = self.engine_dir / "events.jsonl"
        self.lock_path = self.engine_dir / ".lock"
        self.id_path = self.engine_dir / "campaign-id"
        self.key_path = self.engine_dir / "signing.key"

    # -------------------------------------------------------------- key management
    @property
    def campaign_id(self):
        return self.id_path.read_text(encoding="utf-8").strip()

    @property
    def legacy_key_path(self):
        return KEY_DIR / f"{self.campaign_id}.key"

    def _key(self):
        for path in (self.key_path, self.legacy_key_path):
            if path.exists():
                return bytes.fromhex(path.read_text(encoding="utf-8").strip())
        raise TamperError(f"Signing key for this campaign is missing ({self.key_path}). The log can't be trusted. "
                          "If the log itself is fine (e.g. the key was left on another machine), `engine rekey` re-signs it.")

    def init(self):
        self.engine_dir.mkdir(parents=True, exist_ok=True)
        if self.events_path.exists():
            raise FileExistsError("engine already initialised for this campaign")
        cid = secrets.token_hex(8)
        self.id_path.write_text(cid + "\n", encoding="utf-8")
        self.key_path.write_text(secrets.token_hex(32), encoding="utf-8")
        self.events_path.write_text("", encoding="utf-8")

    def rekey(self):
        """Re-sign the log (and its backups) under a fresh in-repo key. Returns the number of events.

        If a key is present, the log must verify under it first. If the key is missing, only the chain's
        structure (sequence numbers and prev links) can be checked, since signatures can't be verified."""
        with self.lock():
            has_key = self.key_path.exists() or self.legacy_key_path.exists()
            if has_key:
                self.load()  # raises TamperError on a genuinely modified log
            events = self._parse_chain(self.events_path)
            key = secrets.token_bytes(32)
            tmp = self.events_path.with_suffix(".jsonl.tmp")
            tmp.write_text("".join(line + "\n" for line in self._sign(events, key)), encoding="utf-8", newline="\n")
            self.key_path.write_text(key.hex(), encoding="utf-8")
            os.replace(tmp, self.events_path)
            bdir = self.engine_dir / "backups"
            for p in sorted(bdir.glob("*.jsonl")) if bdir.is_dir() else []:
                if p.name.startswith("events-tampered"):
                    continue
                try:
                    lines = self._sign(self._parse_chain(p), key)
                except TamperError:
                    continue  # leave an unusable backup as it is
                p.write_text("".join(line + "\n" for line in lines), encoding="utf-8", newline="\n")
            return len(events)

    @staticmethod
    def _parse_chain(path):
        events, prev = [], GENESIS
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    raise TamperError(f"{path.name} line {lineno} is not valid JSON")
                if ev.get("seq") != len(events) + 1 or ev.get("prev") != prev:
                    raise TamperError(f"{path.name} line {lineno}: chain broken (events missing, reordered or edited)")
                prev = ev.get("hash", "")
                events.append(ev)
        return events

    @staticmethod
    def _sign(events, key):
        prev, lines = GENESIS, []
        for ev in events:
            body = {k: v for k, v in ev.items() if k != "hash"}
            body["prev"] = prev
            body["hash"] = hmac.new(key, (prev + canonical(body)).encode(), hashlib.sha256).hexdigest()
            prev = body["hash"]
            lines.append(canonical(body))
        return lines

    # -------------------------------------------------------------- locking
    @contextmanager
    def lock(self, timeout=10.0):
        deadline = time.time() + timeout
        while True:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                break
            except FileExistsError:
                try:  # stale lock (crashed process) older than 30 s
                    if time.time() - self.lock_path.stat().st_mtime > 30:
                        self.lock_path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.time() > deadline:
                    raise TimeoutError("campaign is locked by another engine process")
                time.sleep(0.05)
        try:
            yield
        finally:
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass

    # -------------------------------------------------------------- read / verify
    # Speed: re-checking every signature on every command is most of a command's cost on a long campaign. After a
    # full check the engine keeps a *verified prefix* record (engine/.verified.json): the log's byte length, the
    # SHA-256 of those bytes and the head hash, the record itself signed with the campaign key. A later load whose
    # file starts with exactly those bytes skips re-signing them and verifies only what was appended after. Any edit
    # inside the prefix changes its SHA-256, so the full check runs and tampering is still caught, and the record
    # can't be forged without the key. `engine verify` always checks every event.
    VERIFIED_FILE = ".verified.json"

    def _is_live_log(self):
        return self.events_path == self.engine_dir / "events.jsonl"   # not a backup or quicksave being probed

    def _record_mac(self, key, rec):
        return hmac.new(key, canonical({k: rec[k] for k in ("size", "sha256", "head", "count")}).encode(),
                        hashlib.sha256).hexdigest()

    def _verified_record(self, key, raw):
        if not self._is_live_log():
            return None
        try:
            rec = json.loads((self.engine_dir / self.VERIFIED_FILE).read_text(encoding="utf-8"))
            size = int(rec["size"])
            if not hmac.compare_digest(self._record_mac(key, rec), str(rec.get("mac", ""))):
                return None
            if size > len(raw) or hashlib.sha256(raw[:size]).hexdigest() != rec["sha256"]:
                return None
            return rec
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _save_verified(self, key, raw_or_none, head, count):
        """Record the whole current log as verified (raw bytes given, or re-read from disk)."""
        if not self._is_live_log():
            return
        try:
            raw = raw_or_none if raw_or_none is not None else self.events_path.read_bytes()
            rec = {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "head": head, "count": count}
            rec["mac"] = self._record_mac(key, rec)
            path = self.engine_dir / self.VERIFIED_FILE
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(rec), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass   # only a speed-up: if it can't be written, the next load just verifies more

    def _remember(self, size, head, count, verified, sha=None):
        """What this process last saw of the log, so appending (or catching up) doesn't have to re-read all of it."""
        try:
            mtime = self.events_path.stat().st_mtime_ns
        except OSError:
            mtime = None
        self._seen = {"size": size, "mtime": mtime, "head": head, "count": count, "verified": verified, "sha": sha}

    @staticmethod
    def _check_link(key, ev, prev, n, lineno):
        """Verify one event against the one before it (chain link, sequence number, signature)."""
        body = {k: v for k, v in ev.items() if k != "hash"}
        if ev.get("prev") != prev:
            raise TamperError(f"event #{ev.get('seq')} (line {lineno}) does not follow the previous event — log was edited, reordered or truncated")
        if ev.get("seq") != n + 1:
            raise TamperError(f"line {lineno}: sequence number {ev.get('seq')} out of order")
        expect = hmac.new(key, (prev + canonical(body)).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect, ev.get("hash", "")):
            raise TamperError(f"event #{ev.get('seq')} (line {lineno}) signature mismatch — it was modified outside the engine")

    def load_new(self):
        """The events appended since this process last read or wrote the log, each verified, or None when the log
        changed any other way (shortened, replaced by a quickload, edited): the caller then reloads it in full."""
        seen = getattr(self, "_seen", None)
        if not seen or not seen["verified"] or not seen.get("sha"):
            return None
        key = self._key()
        raw = self.events_path.read_bytes()
        size = seen["size"]
        if len(raw) < size or hashlib.sha256(raw[:size]).hexdigest() != seen["sha"]:
            return None
        new, prev, n = [], seen["head"], seen["count"]
        for bline in raw[size:].split(b"\n"):
            line = bline.decode("utf-8")
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                raise TamperError(f"events.jsonl event #{n + 1} is not valid JSON")
            self._check_link(key, ev, prev, n, f"after #{n}")
            prev, n = ev.get("hash", ""), n + 1
            new.append(ev)
        sha = hashlib.sha256(raw).hexdigest()
        if new:
            self._save_verified(key, raw, prev, n)
        self._remember(len(raw), prev, n, verified=True, sha=sha)
        return new

    def load(self, verify=True, full=False):
        """Return the list of events, verifying the chain. Raises TamperError on any break.

        full=True ignores the verified-prefix record and re-checks every signature (`engine verify`)."""
        if not self.events_path.exists():
            raise FileNotFoundError("this campaign has no engine log; run `python -m engine init`")
        key = self._key() if verify else None
        raw = self.events_path.read_bytes()
        rec = self._verified_record(key, raw) if verify and not full else None
        trusted_n = int(rec["count"]) if rec else 0
        events, prev = [], GENESIS
        for lineno, bline in enumerate(raw.split(b"\n"), 1):
            line = bline.decode("utf-8")
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                raise TamperError(f"events.jsonl line {lineno} is not valid JSON")
            if verify and len(events) >= trusted_n:
                self._check_link(key, ev, prev, len(events), lineno)
            prev = ev.get("hash", "")
            events.append(ev)
            if rec and len(events) == trusted_n and prev != rec["head"]:
                raise TamperError("the verified record doesn't match the log; run `python -m engine verify`")
        if rec and len(events) < trusted_n:
            raise TamperError("the log is shorter than its verified record; run `python -m engine verify`")
        sha = hashlib.sha256(raw).hexdigest()
        if verify and (not rec or len(events) > trusted_n):
            self._save_verified(key, raw, prev, len(events))
        self._remember(len(raw), prev, len(events), verified=verify, sha=sha)
        return events

    def valid_prefix(self):
        """Number of leading events whose signatures verify (for repair after tampering)."""
        key = self._key()
        prev, n = GENESIS, 0
        with open(self.events_path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    break
                body = {k: v for k, v in ev.items() if k != "hash"}
                expect = hmac.new(key, (prev + canonical(body)).encode(), hashlib.sha256).hexdigest()
                if ev.get("prev") != prev or ev.get("seq") != n + 1 or not hmac.compare_digest(expect, ev.get("hash", "")):
                    break
                prev, n = ev["hash"], n + 1
        return n

    def head(self):
        seen = getattr(self, "_seen", None)
        if seen and seen["verified"]:
            try:
                st = self.events_path.stat()
                if st.st_size == seen["size"] and st.st_mtime_ns == seen["mtime"]:
                    return seen["head"], seen["count"]   # nobody has touched the log since this process read or wrote it
            except OSError:
                pass
        events = self.load()
        return (events[-1]["hash"] if events else GENESIS), len(events)

    # -------------------------------------------------------------- write
    def append_many(self, new_events, expected_seq=None):
        """Append events atomically under the lock. Each is {'type':..., 'data':..., ...}."""
        with self.lock():
            prev, seq = self.head()
            if expected_seq is not None and seq != expected_seq:
                raise RuntimeError("the game state changed while this command ran; please retry")
            key = self._key()
            lines, written = [], []
            now = datetime.datetime.now().isoformat(timespec="seconds")
            for ev in new_events:
                seq += 1
                body = {"seq": seq, "ts": now, "prev": prev, **ev}
                body["hash"] = hmac.new(key, (prev + canonical({k: v for k, v in body.items()})).encode(),
                                        hashlib.sha256).hexdigest()
                prev = body["hash"]
                lines.append(canonical(body))
                written.append(body)
            with open(self.events_path, "a", encoding="utf-8", newline="\n") as fh:
                for line in lines:
                    fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            # head() above verified everything before these lines, and these lines were just signed here
            raw = self.events_path.read_bytes()
            self._save_verified(key, raw, prev, seq)
            self._remember(len(raw), prev, seq, verified=True, sha=hashlib.sha256(raw).hexdigest())
            self._backup(seq)
            return written

    def _backup(self, seq):
        """Rotating copies of the signed log. A backup is only trusted if its own signatures verify."""
        bdir = self.engine_dir / "backups"
        bdir.mkdir(exist_ok=True)
        import shutil
        import sys
        import time

        def copy(dst):
            # the events are already durably appended; a backup briefly locked by a reader (the live table,
            # an antivirus scan on Windows) is retried, then skipped with a warning rather than failing the command
            for attempt in range(5):
                try:
                    shutil.copyfile(self.events_path, dst)
                    return
                except OSError as err:
                    if attempt == 4:
                        print(f"⚠ backup {dst.name} not refreshed ({err}); the signed log itself is saved.", file=sys.stderr)
                        return
                    time.sleep(0.1 * (attempt + 1))

        copy(bdir / "latest.jsonl")
        if seq // 50 != (seq - 1) // 50 or not (bdir / f"checkpoint-{seq // 50 % 5}.jsonl").exists():
            copy(bdir / f"checkpoint-{seq // 50 % 5}.jsonl")

    def restore_best_backup(self):
        bdir = self.engine_dir / "backups"
        best, best_n = None, -1
        for p in sorted(bdir.glob("*.jsonl")):
            if p.name.startswith("events-tampered"):
                continue
            tmp = Store(self.dir)
            tmp.events_path = p
            n = tmp.valid_prefix()
            total = sum(1 for l in open(p, encoding="utf-8") if l.strip())
            if n == total and n > best_n:
                best, best_n = p, n
        return best, best_n


def active_dir():
    name = ACTIVE_FILE.read_text(encoding="utf-8").strip() if ACTIVE_FILE.exists() else ""
    path = CAMPAIGNS / name
    if not name or not path.is_dir():
        raise SystemExit('No active campaign. Run: python -m engine campaign new "Title"')
    return path

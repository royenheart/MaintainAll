"""Hermetic tests for daed DNS mode switching.

They use a temporary wing.db. The live deploy/daed/config/wing.db is not opened.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


def load_init():
    path = Path(__file__).resolve().parent / "daed-init.py"
    spec = importlib.util.spec_from_file_location("daed_init", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


INIT = load_init()

DNS = """dns {
upstream {
  alidns: 'udp://223.5.5.5:53'
  googledns: 'tcp+udp://8.8.8.8:53'
}
routing {
  request {
    qname(geosite:cn) -> alidns
    fallback: googledns
  }
}
}
"""

GLOBAL = """global {
  lan_interface:"eth0,docker0"
  udp_check_dns:"dns.google:53,8.8.8.8,2001:4860:4860::8888"
  fallback_resolver:"223.5.5.5:53"
  bandwidth_max_tx:"200 mbps"
}
"""

ROUTING = """routing {
pname(daed) -> must_direct
pname(NetworkManager, systemd-resolved, dnsmasq) -> must_direct
# ── private-rules:start ──
domain(suffix: example.test) -> proxy
# ── private-rules:end ──
fallback: proxy
}
"""


def make_db(directory: Path) -> Path:
    db = directory / "wing.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE dns (
          id integer PRIMARY KEY,
          name text NOT NULL DEFAULT '',
          dns text NOT NULL,
          selected numeric NOT NULL,
          version integer NOT NULL DEFAULT 0
        );
        CREATE TABLE configs (
          id integer PRIMARY KEY,
          name text NOT NULL DEFAULT '',
          "global" text NOT NULL,
          selected numeric NOT NULL,
          version integer NOT NULL DEFAULT 0
        );
        CREATE TABLE routings (
          id integer PRIMARY KEY,
          name text NOT NULL DEFAULT '',
          routing text NOT NULL,
          selected numeric NOT NULL,
          version integer NOT NULL DEFAULT 0
        );
        CREATE TABLE marker (id integer PRIMARY KEY, note text NOT NULL);
        """
    )
    conn.execute(
        "INSERT INTO dns (name, dns, selected, version) VALUES ('default', ?, 1, 4)",
        (DNS,),
    )
    conn.execute(
        'INSERT INTO configs (name, "global", selected, version) VALUES (\'global\', ?, 1, 8)',
        (GLOBAL,),
    )
    conn.execute(
        "INSERT INTO routings (name, routing, selected, version) VALUES ('default', ?, 1, 3)",
        (ROUTING,),
    )
    conn.execute("INSERT INTO marker (note) VALUES ('keep')")
    conn.commit()
    conn.close()
    return db


def selected(db: Path, table: str, column: str) -> tuple[str, int]:
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            f'SELECT "{column}", version FROM {table} WHERE selected = 1'
        ).fetchone()
    finally:
        conn.close()
    return row[0], row[1]


class TextPatchTest(unittest.TestCase):
    def test_fallback_preserves_compact_and_spaced_styles(self) -> None:
        compact = INIT.set_fallback_resolver(GLOBAL, "8.8.8.8:53")
        self.assertIn('fallback_resolver:"8.8.8.8:53"', compact)
        self.assertIn('lan_interface:"eth0,docker0"', compact)
        spaced = 'fallback_resolver: "223.5.5.5:53"\n'
        self.assertEqual(
            INIT.set_fallback_resolver(spaced, "1.1.1.1:53"),
            'fallback_resolver: "1.1.1.1:53"\n',
        )

    def test_systemd_resolved_round_trip_keeps_private_rules(self) -> None:
        entered = INIT.set_systemd_resolved(ROUTING, enter_daed=True)
        self.assertNotIn("systemd-resolved", entered)
        self.assertIn("pname(NetworkManager, dnsmasq) -> must_direct", entered)
        self.assertIn("domain(suffix: example.test) -> proxy", entered)
        restored = INIT.set_systemd_resolved(entered, enter_daed=False)
        self.assertIn(
            "pname(NetworkManager, systemd-resolved, dnsmasq) -> must_direct",
            restored,
        )
        self.assertIn("domain(suffix: example.test) -> proxy", restored)

    def test_template_file_is_not_rewritten(self) -> None:
        path = INIT.CONFIG_DIR / "routing.conf"
        before = path.read_text(encoding="utf-8")
        INIT.set_systemd_resolved(before, enter_daed=True)
        self.assertEqual(path.read_text(encoding="utf-8"), before)
        foreign = INIT.CONFIG_DIR / "dns.conf.foreign-doh"
        foreign_before = foreign.read_text(encoding="utf-8")
        body = INIT.render_dns_body("doh", "1.1.1.1")
        self.assertIn("https://1.1.1.1/dns-query", body)
        self.assertNotIn("https://8.8.8.8/dns-query", body)
        self.assertEqual(foreign.read_text(encoding="utf-8"), foreign_before)


class SwitchTest(unittest.TestCase):
    def test_switch_to_doh_and_back_preserves_unrelated_rows(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = make_db(Path(raw))
            self.assertEqual(INIT.switch_dns_mode(db, "doh", timeout=2), 0)
            dns, dns_version = selected(db, "dns", "dns")
            global_text, global_version = selected(db, "configs", "global")
            routing, routing_version = selected(db, "routings", "routing")
            self.assertIn("https://8.8.8.8/dns-query", dns)
            self.assertIn("udp://223.5.5.5:53", dns)
            self.assertNotIn("tcp+udp://8.8.8.8:53", dns)
            self.assertIn('fallback_resolver:"8.8.8.8:53"', global_text)
            self.assertIn('udp_check_dns:"dns.google:53,8.8.8.8,2001:4860:4860::8888"', global_text)
            self.assertIn('lan_interface:"eth0,docker0"', global_text)
            self.assertNotIn("systemd-resolved", routing)
            self.assertIn("domain(suffix: example.test) -> proxy", routing)
            self.assertGreater(dns_version, 4)
            self.assertGreater(global_version, 8)
            self.assertGreater(routing_version, 3)
            self.assertEqual(len(list(Path(raw).glob("wing.db.bak-*"))), 1)

            dns_version_now = dns_version
            self.assertEqual(INIT.switch_dns_mode(db, "doh", timeout=2), 0)
            _, again = selected(db, "dns", "dns")
            self.assertEqual(again, dns_version_now)
            self.assertEqual(len(list(Path(raw).glob("wing.db.bak-*"))), 1)

            self.assertEqual(INIT.switch_dns_mode(db, "direct", timeout=2), 0)
            dns, _ = selected(db, "dns", "dns")
            global_text, _ = selected(db, "configs", "global")
            routing, _ = selected(db, "routings", "routing")
            self.assertIn("tcp+udp://8.8.8.8:53", dns)
            self.assertNotIn("https://8.8.8.8/dns-query", dns)
            self.assertIn('fallback_resolver:"223.5.5.5:53"', global_text)
            self.assertIn(
                "pname(NetworkManager, systemd-resolved, dnsmasq) -> must_direct",
                routing,
            )
            self.assertIn("domain(suffix: example.test) -> proxy", routing)
            conn = sqlite3.connect(db)
            try:
                note = conn.execute("SELECT note FROM marker").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(note, "keep")

    def test_cloudflare_address(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = make_db(Path(raw))
            self.assertEqual(INIT.switch_dns_mode(db, "doh", doh_ip="1.1.1.1", timeout=2), 0)
            dns, _ = selected(db, "dns", "dns")
            global_text, _ = selected(db, "configs", "global")
            self.assertIn("https://1.1.1.1/dns-query", dns)
            self.assertNotIn("https://8.8.8.8/dns-query", dns)
            self.assertIn('fallback_resolver:"1.1.1.1:53"', global_text)

    def test_locked_database_is_left_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = make_db(Path(raw))
            holder = sqlite3.connect(db)
            holder.execute("BEGIN EXCLUSIVE")
            try:
                code = INIT.switch_dns_mode(db, "doh", timeout=0.2)
            finally:
                holder.rollback()
                holder.close()
            self.assertEqual(code, 1)
            dns, version = selected(db, "dns", "dns")
            self.assertIn("tcp+udp://8.8.8.8:53", dns)
            self.assertEqual(version, 4)
            self.assertEqual(list(Path(raw).glob("wing.db.bak-*")), [])

    def test_reformatted_same_mode_is_not_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = make_db(Path(raw))
            custom = DNS.replace(
                "fallback: googledns",
                "qname(geosite:category-ads-all) -> reject\n    fallback: googledns",
            )
            conn = sqlite3.connect(db)
            conn.execute("UPDATE dns SET dns = ? WHERE selected = 1", (custom,))
            conn.commit()
            conn.close()
            self.assertEqual(INIT.switch_dns_mode(db, "direct", timeout=2), 0)
            dns, version = selected(db, "dns", "dns")
            self.assertIn("category-ads-all", dns)
            self.assertEqual(version, 4)

    def test_seed_skips_nonempty_table(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = make_db(Path(raw))
            conn = sqlite3.connect(db)
            try:
                wrote = INIT.seed_config(
                    conn, "dns", "dns", "dns", INIT.CONFIG_DIR / "dns.conf.foreign-doh"
                )
                conn.commit()
            finally:
                conn.close()
            self.assertFalse(wrote)
            dns, version = selected(db, "dns", "dns")
            self.assertIn("tcp+udp://8.8.8.8:53", dns)
            self.assertEqual(version, 4)


if __name__ == "__main__":
    unittest.main()

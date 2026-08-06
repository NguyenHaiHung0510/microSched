import textwrap
from datetime import UTC, datetime, timedelta

import app.core.process_stats as process_stats
from app.core.process_stats import (
    calculate_rss_pct,
    read_mem_total_kb,
    read_rss_kb,
    read_uptime_s,
    restart_advised,
)


def test_parse_vmrss_from_fake_file(tmp_path) -> None:
    fake = tmp_path / "status"
    fake.write_text(
        textwrap.dedent("""\
            Name:\tpython3
            VmPeak:\t  102400 kB
            VmRSS:\t  51234 kB
            VmSize:\t  98765 kB
        """)
    )
    assert read_rss_kb(path=str(fake)) == 51234


def test_missing_file_returns_none(tmp_path) -> None:
    assert read_rss_kb(path=str(tmp_path / "no_such_file")) is None


def test_garbage_content_returns_none(tmp_path) -> None:
    fake = tmp_path / "status"
    fake.write_text("this is not a proc status file\\nrandom garbage\\n")
    assert read_rss_kb(path=str(fake)) is None


def test_uptime_uses_process_import_time_and_wall_clock(monkeypatch) -> None:
    started_at = datetime(2026, 7, 26, 1, 2, 3, tzinfo=UTC)
    monkeypatch.setattr(process_stats, "_PROCESS_STARTED_AT", started_at)
    assert read_uptime_s(now=started_at + timedelta(seconds=123)) == 123


def test_mem_total_uses_smaller_cgroup_or_proc_reading(tmp_path) -> None:
    cgroup_v2 = tmp_path / "memory.max"
    cgroup_v2.write_text(str(256 * 1024))
    cgroup_v1 = tmp_path / "memory.limit_in_bytes"
    cgroup_v1.write_text(str(1024 * 1024))
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       512 kB\\n")

    assert (
        read_mem_total_kb(
            cgroup_v2_path=str(cgroup_v2),
            cgroup_v1_path=str(cgroup_v1),
            meminfo_path=str(meminfo),
        )
        == 256
    )


def test_rss_percentage_and_restart_threshold() -> None:
    assert calculate_rss_pct(899, 1000) == 89.9
    assert restart_advised(89.9) is False
    assert restart_advised(90.0) is True
    assert restart_advised(90.1) is True
    assert calculate_rss_pct(42, None) is None
    assert restart_advised(None) is None

from gateway.scripts import metrics_to_prom


def test_render_prometheus_text_groups_by_tags_and_status():
    rows = [
        {
            "ts": "2026-01-01T00:00:00Z",
            "status": "ok",
            "cursor": 10,
            "pages": 2,
            "wrote_rows": 5,
            "skipped_duplicates": 1,
            "duration_seconds": 0.5,
            "tags": {"env": "prod", "region": "sg"},
        },
        {
            "ts": "2026-01-01T00:10:00Z",
            "status": "error",
            "cursor": 10,
            "pages": 1,
            "wrote_rows": 0,
            "skipped_duplicates": 0,
            "duration_seconds": 0.2,
            "tags": {"env": "prod", "region": "sg"},
        },
        {
            "ts": "2026-01-01T00:20:00Z",
            "status": "ok",
            "cursor": 20,
            "pages": 3,
            "wrote_rows": 8,
            "skipped_duplicates": 2,
            "duration_seconds": 0.8,
            "tags": {"env": "staging"},
        },
    ]

    text = metrics_to_prom.render_prometheus_text(rows)

    assert 'mmdev_sync_runs_total{env="prod",region="sg",status="ok"} 1' in text
    assert 'mmdev_sync_runs_total{env="prod",region="sg",status="error"} 1' in text
    assert 'mmdev_sync_rows_written_total{env="prod",region="sg"} 5' in text
    assert 'mmdev_sync_duplicates_skipped_total{env="prod",region="sg"} 1' in text
    assert 'mmdev_sync_last_run_success{env="prod",region="sg"} 0' in text
    assert 'mmdev_sync_last_cursor{env="staging"} 20' in text


def test_parse_ts_epoch_and_label_sanitize():
    assert metrics_to_prom.parse_ts_epoch("2026-01-01T00:00:00Z") > 0
    assert metrics_to_prom.parse_ts_epoch("bad-time") == 0
    assert metrics_to_prom.sanitize_label_key("1-env.name") == "tag_1_env_name"


def test_write_output_supports_atomic_and_non_atomic(tmp_path):
    path = tmp_path / "metrics.prom"
    path.write_text("old", encoding="utf-8")
    metrics_to_prom.write_output(path, "atomic", atomic_write=True, output_mode="replace")
    assert path.read_text(encoding="utf-8") == "atomic"
    assert not list(tmp_path.glob("*.tmp"))

    metrics_to_prom.write_output(path, "plain", atomic_write=False, output_mode="replace")
    assert path.read_text(encoding="utf-8") == "plain"


def test_write_output_supports_append_mode(tmp_path):
    path = tmp_path / "metrics.prom"
    metrics_to_prom.write_output(path, "line1\n", output_mode="append")
    metrics_to_prom.write_output(path, "line2\n", output_mode="append")
    assert path.read_text(encoding="utf-8") == "line1\nline2\n"


def test_write_output_append_mode_respects_max_append_lines(tmp_path):
    path = tmp_path / "metrics.prom"
    metrics_to_prom.write_output(path, "l1\nl2\n", output_mode="append", max_append_lines=0)
    metrics_to_prom.write_output(path, "l3\nl4\n", output_mode="append", max_append_lines=3)
    assert path.read_text(encoding="utf-8") == "l2\nl3\nl4\n"


def test_write_output_append_mode_respects_max_append_bytes(tmp_path):
    path = tmp_path / "metrics.prom"
    metrics_to_prom.write_output(path, "aaa\nbbb\n", output_mode="append", max_append_bytes=0)
    metrics_to_prom.write_output(path, "ccc\nddd\n", output_mode="append", max_append_bytes=10)
    content = path.read_text(encoding="utf-8")
    assert len(content.encode("utf-8")) <= 10
    assert content.endswith("\n")


def test_maybe_write_output_supports_dry_run(tmp_path):
    path = tmp_path / "metrics.prom"
    wrote = metrics_to_prom.maybe_write_output(
        path,
        "a\nb\n",
        dry_run=True,
        atomic_write=True,
        output_mode="replace",
        max_append_lines=0,
        max_append_bytes=0,
    )
    assert wrote is False
    assert not path.exists()


def test_count_non_comment_lines():
    text = "# HELP x\n# TYPE x gauge\nmetric_a 1\n\nmetric_b 2\n"
    assert metrics_to_prom.count_non_comment_lines(text) == 2


def test_render_prometheus_text_supports_window_hours():
    rows = [
        {
            "ts": "2026-01-01T00:00:00Z",
            "status": "ok",
            "cursor": 10,
            "pages": 2,
            "wrote_rows": 5,
            "skipped_duplicates": 1,
            "duration_seconds": 0.5,
            "tags": {"env": "prod"},
        },
        {
            "ts": "2026-01-01T10:00:00Z",
            "status": "error",
            "cursor": 10,
            "pages": 1,
            "wrote_rows": 0,
            "skipped_duplicates": 0,
            "duration_seconds": 0.2,
            "tags": {"env": "prod"},
        },
    ]

    # now=2026-01-01T12:00:00Z, keep only recent 6 hours -> only 10:00 event.
    text = metrics_to_prom.render_prometheus_text(rows, window_hours=6, now_epoch=1767268800)
    assert 'mmdev_sync_runs_total{env="prod",status="ok"} 0' in text
    assert 'mmdev_sync_runs_total{env="prod",status="error"} 1' in text


def test_render_prometheus_text_supports_group_by_subset():
    rows = [
        {
            "ts": "2026-01-01T00:00:00Z",
            "status": "ok",
            "cursor": 10,
            "pages": 2,
            "wrote_rows": 5,
            "skipped_duplicates": 1,
            "duration_seconds": 0.5,
            "tags": {"env": "prod", "region": "sg"},
        },
        {
            "ts": "2026-01-01T00:10:00Z",
            "status": "ok",
            "cursor": 11,
            "pages": 1,
            "wrote_rows": 3,
            "skipped_duplicates": 0,
            "duration_seconds": 0.2,
            "tags": {"env": "prod", "region": "us"},
        },
    ]

    text = metrics_to_prom.render_prometheus_text(rows, group_by={"env"})
    assert 'mmdev_sync_rows_written_total{env="prod"} 8' in text
    assert 'region="sg"' not in text
    assert 'region="us"' not in text


def test_parse_group_by_sanitizes_keys():
    result = metrics_to_prom.parse_group_by("env, 1-region.name, ,")
    assert result == {"env", "tag_1_region_name"}


def test_render_prometheus_text_emit_zero_series_when_empty_window():
    rows = [
        {
            "ts": "2026-01-01T00:00:00Z",
            "status": "ok",
            "cursor": 10,
            "pages": 2,
            "wrote_rows": 5,
            "skipped_duplicates": 1,
            "duration_seconds": 0.5,
            "tags": {"env": "prod", "region": "sg"},
        }
    ]
    # now=2026-01-02T00:00:00Z, 1-hour window excludes the row.
    text = metrics_to_prom.render_prometheus_text(
        rows,
        window_hours=1,
        now_epoch=1767312000,
        group_by={"env"},
        emit_zero_series=True,
        zero_series_labels={"env": "prod", "region": "sg"},
    )
    assert 'mmdev_sync_runs_total{env="prod",status="ok"} 0' in text
    assert 'mmdev_sync_runs_total{env="prod",status="error"} 0' in text
    assert 'mmdev_sync_rows_written_total{env="prod"} 0' in text


def test_parse_label_kv_csv_ignores_invalid_parts():
    labels = metrics_to_prom.parse_label_kv_csv("env=prod,invalid,region=sg,=oops, 1-a=b ")
    assert labels == {"env": "prod", "region": "sg", "tag_1_a": "b"}

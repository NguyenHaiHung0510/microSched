"""The release packet is generated offline from synthetic/private test inputs."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from scripts import prepare_migarden_commission as commission


def test_offline_packet_has_token_only_in_private_file_and_reviewable_cas_sql(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(commission, "CHECKOUT", tmp_path)
    state = tmp_path / "expected.json"
    state.write_text(
        json.dumps(
            dict(
                device_id=None,
                device_environment=None,
                token_hash=None,
                revoked_at=None,
            )
        ),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        operation="issue",
        environment="production",
        device_id="prod-controller-synthetic",
        expected_database="synthetic_production",
        expected_host="db.example.invalid",
        expected_port=5432,
        expected_state_file=state,
        output_dir=tmp_path / ".local" / "packet",
    )
    commission.prepare(args)
    token = (args.output_dir / "device.token").read_text(encoding="ascii").strip()
    assert len(token) == 43
    assert commission.TOKEN.fullmatch(token)
    sql = (args.output_dir / "binding.sql").read_text(encoding="ascii")
    plan = json.loads((args.output_dir / "plan.json").read_text(encoding="ascii"))
    assert token not in sql and token not in json.dumps(plan)
    assert hashlib.sha256(token.encode()).hexdigest() in sql
    assert "IS DISTINCT FROM" in sql and "unresolved execution" in sql
    assert "microsched.audit_log" in sql and "COMMIT" in sql
    assert (
        plan["sql_sha256"]
        == hashlib.sha256((args.output_dir / "binding.sql").read_bytes()).hexdigest()
    )
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "N01 Synthetic Test Root")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    network = tmp_path / "synthetic-network.json"
    network.write_text(
        json.dumps(
            {
                "wifi_ssid": "synthetic-qa",
                "wifi_password": "synthetic-only-fixture",
                "base_url": "https://api.example.invalid",
                "ca_pem": certificate.public_bytes(serialization.Encoding.PEM).decode("ascii"),
            }
        ),
        encoding="utf-8",
    )
    commission.profile(
        SimpleNamespace(
            plan_dir=args.output_dir,
            network_file=network,
            fixture_verified=False,
        )
    )
    raw = (args.output_dir / "release-profile.json").read_bytes()
    assert not raw.startswith(bytes.fromhex("efbbbf"))
    profile = json.loads(raw)
    assert profile["device_id"] == args.device_id and profile["device_token"] == token
    assert profile["fixture_verified"] is False
    assert len(profile) == 7
    monkeypatch.setenv(
        "MIGARDEN_COMMISSION_DATABASE_URL",
        "postgresql://microsched_app:synthetic@wrong.example.invalid/synthetic_production",
    )
    monkeypatch.setattr(
        commission.psycopg, "connect", lambda *a, **kw: pytest.fail("wrong target connected")
    )
    with pytest.raises(ValueError, match="target differs"):
        commission.apply_plan(SimpleNamespace(plan_dir=args.output_dir))


def test_prepared_rotation_never_overwrites_active_or_unknown_identity():
    state = dict(
        device_id="prod-controller-synthetic",
        device_environment="production",
        token_hash="a" * 64,
        revoked_at=None,
    )
    with pytest.raises(ValueError, match="revoke"):
        commission.transaction(
            action="issue",
            environment="production",
            device_id=state["device_id"],
            database="synthetic",
            expected=state,
            token_hash="b" * 64,
            operation_id="rotation",
        )
    with pytest.raises(ValueError, match="different environment"):
        commission.expected_state(state | {"device_environment": "qa"}, "production")


def qa_issue_args(tmp_path, *, host="127.0.0.1", port=21894, database="microsched_n01_test"):
    state = tmp_path / "qa-old.json"
    state.write_text(json.dumps(dict.fromkeys(commission.STATE_KEYS)), encoding="ascii")
    return SimpleNamespace(
        operation="issue",
        environment="qa",
        device_id="qa-controller-synthetic",
        expected_database=database,
        expected_host=host,
        expected_port=port,
        expected_state_file=state,
        output_dir=tmp_path / ".local" / "qa",
    )


def test_qa_prepare_requires_loopback_n01_target_before_creating_packet(tmp_path, monkeypatch):
    monkeypatch.setattr(commission, "CHECKOUT", tmp_path)
    args = qa_issue_args(tmp_path, host="db.example.invalid")
    with pytest.raises(ValueError, match="QA target"):
        commission.prepare(args)
    assert not args.output_dir.exists()


def test_qa_apply_revalidates_forged_matching_plan_before_connect(tmp_path, monkeypatch):
    monkeypatch.setattr(commission, "CHECKOUT", tmp_path)
    args = qa_issue_args(tmp_path)
    commission.prepare(args)
    path = args.output_dir / "plan.json"
    data = json.loads(path.read_text(encoding="ascii"))
    data["expected_host"] = "db.example.invalid"
    path.write_text(json.dumps(data), encoding="ascii")
    monkeypatch.setenv(
        "MIGARDEN_COMMISSION_DATABASE_URL",
        "postgresql://microsched_app:synthetic@db.example.invalid:21894/microsched_n01_test",
    )
    monkeypatch.setattr(
        commission.psycopg,
        "connect",
        lambda *a, **kw: pytest.fail("nonlocal QA target reached connector"),
    )
    with pytest.raises(ValueError, match="QA target"):
        commission.apply_plan(SimpleNamespace(plan_dir=args.output_dir))


@pytest.mark.parametrize("override", ["PGSERVICE", "PGSERVICEFILE", "PGHOSTADDR", "PGOPTIONS"])
def test_qa_apply_refuses_libpq_override_before_connect(tmp_path, monkeypatch, override):
    monkeypatch.setattr(commission, "CHECKOUT", tmp_path)
    args = qa_issue_args(tmp_path)
    commission.prepare(args)
    monkeypatch.setenv(
        "MIGARDEN_COMMISSION_DATABASE_URL",
        "postgresql://microsched_app:synthetic@127.0.0.1:21894/microsched_n01_test",
    )
    monkeypatch.setenv(override, "synthetic-forbidden-setting")
    monkeypatch.setattr(
        commission.psycopg, "connect", lambda *a, **kw: pytest.fail("override reached connector")
    )
    with pytest.raises(ValueError, match="QA target"):
        commission.apply_plan(SimpleNamespace(plan_dir=args.output_dir))


@pytest.mark.parametrize(
    "suffix",
    [
        "/not_a_local_n01_database",
        "/microsched_n01_test?hostaddr=192.0.2.1",
        "/microsched_n01_test?service=synthetic",
        "/microsched_n01_test?port=6432",
        "/microsched_n01_test?sslmode=disable",
    ],
)
def test_qa_apply_refuses_wrong_database_or_query_options(tmp_path, monkeypatch, suffix):
    monkeypatch.setattr(commission, "CHECKOUT", tmp_path)
    args = qa_issue_args(tmp_path)
    commission.prepare(args)
    monkeypatch.setenv(
        "MIGARDEN_COMMISSION_DATABASE_URL",
        "postgresql://microsched_app:synthetic@127.0.0.1:21894" + suffix,
    )
    monkeypatch.setattr(
        commission.psycopg, "connect", lambda *a, **kw: pytest.fail("unreviewed target connected")
    )
    with pytest.raises(ValueError, match="QA target|target differs"):
        commission.apply_plan(SimpleNamespace(plan_dir=args.output_dir))

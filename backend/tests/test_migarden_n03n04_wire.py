"""The app consumes the same synthetic transport vectors as the firmware."""

import json
from pathlib import Path

from app.domain.migarden.health import HealthSample
from app.domain.migarden.wire import ExchangeEnvelope, ExchangeOut


def test_shared_wire_old_new_and_optional_health():
    path = Path(__file__).parent / "fixtures/migarden/quiet-health.vectors.json"
    vectors = json.loads(path.read_text(encoding="utf-8"))
    for vector in vectors:
        document = vector["document"]
        if "snapshot" in document:
            packet = ExchangeEnvelope.model_validate(document)
            assert packet.protocol == "migarden.zone-a.v1"
            if vector["name"] == "negotiated_health":
                assert HealthSample.model_validate(packet.health).boot_id == packet.boot_id
        elif "server_time" in document:
            ExchangeOut.model_validate(
                {key: value for key, value in document.items() if key != "extension"}
            )
    wait = next(v["document"] for v in vectors if v["name"] == "neutral_wait")
    assert set(wait) == {"protocol", "retry_after_seconds"}

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from datetime import UTC, datetime

from service_orchestrator.application_processing.domain.entities import Application
from service_orchestrator.service_catalog.domain.entities import Service
from service_orchestrator.shared.domain.ids import new_id
from service_orchestrator.shared.infrastructure.log_config import (
    JsonFormatter,
    TextFormatter,
    configure_logging,
    request_id_var,
)

NOW = datetime(2026, 10, 21, tzinfo=UTC)


class TestUuidV7:
    def test_ids_are_rfc_9562_version_7(self) -> None:
        identifier = new_id()
        assert identifier.version == 7
        assert identifier.variant == uuid.RFC_4122

    def test_ids_are_unique_and_sort_in_creation_order(self) -> None:
        ids = [new_id() for _ in range(2000)]
        assert ids == sorted(ids)
        assert len(set(ids)) == len(ids)

    def test_ids_embed_the_creation_time(self) -> None:
        before = time.time_ns() // 1_000_000
        identifier = new_id()
        after = time.time_ns() // 1_000_000
        assert before <= identifier.int >> 80 <= after + 1

    def test_entities_get_version_7_ids(self) -> None:
        service = Service.register(code="delivery", name="Delivery", description="", now=NOW)
        draft = service.create_draft({}, now=NOW)
        application = Application.start(service_version_id=draft.id, data={}, now=NOW)
        assert {service.id.version, draft.id.version, application.id.version} == {7}


def make_record(**extra: object) -> logging.LogRecord:
    token = request_id_var.set("req-1")
    try:
        configure_logging()
        return logging.getLogger("service_orchestrator.test").makeRecord(
            "service_orchestrator.test",
            logging.INFO,
            __file__,
            1,
            "hello %s",
            ("world",),
            None,
            extra=extra,
        )
    finally:
        request_id_var.reset(token)


class TestLogFormat:
    def test_text_lines_carry_request_id_and_fields(self) -> None:
        line = TextFormatter().format(make_record(service="delivery", version=2, note="two words"))
        assert line.endswith(
            "INFO    service_orchestrator.test [req-1] hello world "
            'service=delivery version=2 note="two words"'
        )

    def test_json_lines_are_machine_readable(self) -> None:
        document = json.loads(JsonFormatter().format(make_record(errors=["/a:required"])))
        assert document["level"] == "INFO"
        assert document["logger"] == "service_orchestrator.test"
        assert document["message"] == "hello world"
        assert document["request_id"] == "req-1"
        assert document["errors"] == ["/a:required"]

    def test_exceptions_include_the_traceback(self) -> None:
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            record = logging.getLogger("x").makeRecord(
                "x", logging.ERROR, __file__, 1, "failed", (), exc_info=sys.exc_info()
            )
        assert "RuntimeError: boom" in json.loads(JsonFormatter().format(record))["exception"]
        assert "Traceback" in TextFormatter().format(record)

    def test_configuring_twice_keeps_one_handler(self) -> None:
        configure_logging()
        configure_logging("DEBUG", "json")
        logger = logging.getLogger("service_orchestrator")
        ours = [h for h in logger.handlers if h.get_name() == "service_orchestrator"]
        assert len(ours) == 1
        assert isinstance(ours[0].formatter, JsonFormatter)
        assert logger.level == logging.DEBUG
        configure_logging()

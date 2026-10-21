from __future__ import annotations

from service_orchestrator.shared.application.payload_checker import PayloadChecker


def codes(evaluation) -> list[tuple[str, str]]:
    return [(e.path, e.code) for e in evaluation.errors]


class TestDelivery:
    def test_fixed_fee_only(self, payload_checker: PayloadChecker, delivery_definition) -> None:
        result = payload_checker.evaluate(delivery_definition, {"distanceKm": 12, "weightKg": 2})
        assert result.valid
        assert result.fees.to_snapshot() == {
            "currency": "KHR",
            "items": [
                {
                    "code": "BASE",
                    "amount": 5000,
                    "label": {"en": "Delivery"},
                    "quantity": None,
                    "unitAmount": None,
                }
            ],
            "total": 5000,
        }

    def test_conditional_express_surcharge(self, payload_checker, delivery_definition) -> None:
        result = payload_checker.evaluate(
            delivery_definition, {"distanceKm": 12, "weightKg": 2, "express": True}
        )
        assert [i["code"] for i in result.fees.to_snapshot()["items"]] == ["BASE", "EXPRESS"]
        assert result.fees.total.amount == 8000

    def test_cross_field_assertion(self, payload_checker, delivery_definition) -> None:
        result = payload_checker.evaluate(
            delivery_definition, {"distanceKm": 80, "weightKg": 2, "express": True}
        )
        assert codes(result) == [("/distanceKm", "assertion_failed")]
        assert result.errors[0].rule_id == "express-max-distance"
        assert result.errors[0].message == "Express delivery is only available up to 50 km."
        assert result.fees is None

    def test_assertions_wait_for_a_valid_schema(self, payload_checker, delivery_definition) -> None:
        result = payload_checker.evaluate(delivery_definition, {"distanceKm": 80, "express": True})
        assert codes(result) == [("/weightKg", "required")]


class TestEventRegistration:
    BASE = {"fullName": "Dara", "email": "dara@example.com", "sessions": ["keynote"]}

    def test_conditional_required_and_visibility(self, payload_checker, event_registration) -> None:
        definition = event_registration["definition"]
        data = {**self.BASE, "attendeeType": "corporate", "studentId": "S-1234"}
        assert codes(payload_checker.evaluate(definition, data)) == [
            ("/studentId", "not_applicable"),
            ("/companyName", "required"),
        ]

    def test_conditional_required_reported_alongside_schema_errors(
        self, payload_checker, event_registration
    ) -> None:
        definition = event_registration["definition"]
        data = {"attendeeType": "student", "sessions": ["keynote"]}
        assert codes(payload_checker.evaluate(definition, data)) == [
            ("/email", "required"),
            ("/fullName", "required"),
            ("/studentId", "required"),
        ]

    def test_conditional_fees(self, payload_checker, event_registration) -> None:
        definition = event_registration["definition"]
        data = {
            **self.BASE,
            "attendeeType": "student",
            "studentId": "S-1234",
            "sessions": ["keynote", "workshop-b"],
        }
        snapshot = payload_checker.evaluate(definition, data).fees.to_snapshot()
        assert [(i["code"], i["amount"]) for i in snapshot["items"]] == [
            ("STUDENT", 10000),
            ("WORKSHOP_B", 20000),
        ]
        assert snapshot["total"] == 30000

    def test_array_assertion(self, payload_checker, event_registration) -> None:
        data = {
            **self.BASE,
            "attendeeType": "professional",
            "sessions": ["workshop-a", "workshop-b"],
        }
        result = payload_checker.evaluate(event_registration["definition"], data)
        assert codes(result) == [("/sessions", "assertion_failed")]


class TestEquipmentRental:
    def test_add_ons_and_nested_fields(self, payload_checker, equipment_rental) -> None:
        data = {
            "equipmentCategory": "camera",
            "durationDays": 20,
            "startDate": "2026-11-01",
            "insurance": True,
            "delivery": {"address": "12 Street 240, Phnom Penh"},
        }
        result = payload_checker.evaluate(equipment_rental["definition"], data)
        assert [(line.code, line.amount.amount) for line in result.fees.lines] == [
            ("CAMERA", 1_200_000),
            ("SERVICE", 20_000),
            ("INSURANCE", 120_000),
            ("DELIVERY", 8_000),
        ]
        assert result.fees.total.amount == 1_348_000

    def test_insurance_minimum_and_flat_service_bracket(self, payload_checker, equipment_rental):
        data = {
            "equipmentCategory": "lighting",
            "durationDays": 3,
            "startDate": "2026-11-01",
            "insurance": True,
        }
        result = payload_checker.evaluate(equipment_rental["definition"], data)
        assert [(line.code, line.amount.amount) for line in result.fees.lines] == [
            ("LIGHTING", 120_000),
            ("SERVICE", 5_000),
            ("INSURANCE", 15_000),
        ]

    def test_long_rental_requires_insurance(self, payload_checker, equipment_rental) -> None:
        data = {"equipmentCategory": "audio", "durationDays": 20, "startDate": "2026-11-01"}
        assert codes(payload_checker.evaluate(equipment_rental["definition"], data)) == [
            ("/insurance", "assertion_failed")
        ]


def test_fee_calculation_errors_become_field_errors(payload_checker) -> None:
    definition = {
        "dataSchema": {"type": "object", "properties": {"bags": {"type": "integer"}}},
        "fees": [
            {
                "code": "BAGS",
                "currency": "KHR",
                "perUnit": {"unitAmount": 2000, "quantity": {"var": "bags"}},
            }
        ],
    }
    result = payload_checker.evaluate(definition, {})
    assert codes(result) == [("", "fee_calculation_failed")]
    assert "'BAGS'" in result.errors[0].message
    assert result.fees is None


def test_evaluation_errors_become_field_errors(payload_checker) -> None:
    definition = {
        "dataSchema": {"type": "object", "properties": {"a": {"type": "number"}}},
        "rules": [
            {
                "id": "ratio",
                "type": "assert",
                "assert": {"<": [{"/": [1, {"var": "a"}]}, 1]},
                "path": "/a",
                "message": "a must be greater than 1",
            }
        ],
    }
    result = payload_checker.evaluate(definition, {"a": 0})
    assert codes(result) == [("/a", "rule_evaluation_failed")]

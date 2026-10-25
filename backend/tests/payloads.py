"""Complete example answers shared by unit and HTTP lifecycle tests."""

PAYLOADS = {
    "delivery": {"distanceKm": 12, "weightKg": 2, "express": True},
    "event_registration": {
        "fullName": "Sokha",
        "email": "sokha@example.com",
        "attendeeType": "corporate",
        "companyName": "Acme",
        "sessions": ["keynote", "workshop-a"],
    },
    "equipment_rental": {
        "equipmentCategory": "camera",
        "durationDays": 10,
        "startDate": "2026-11-02",
        "insurance": True,
        "delivery": {"address": "Phnom Penh", "phone": "+855 12345678"},
    },
}

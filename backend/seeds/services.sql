BEGIN;

INSERT INTO services (id, code, name, description, created_at)
VALUES
    ('01a15bc1-f400-7001-8000-000000000001', 'delivery', 'Parcel Delivery',
     'Book a parcel delivery. Express delivery costs extra and is limited to 50 km.', now()),
    ('01a15bc1-f400-7001-8000-000000000002', 'event-registration', 'Conference Registration',
     'Register for the conference and choose sessions. Fees depend on attendee type and workshops.', now()),
    ('01a15bc1-f400-7001-8000-000000000003', 'equipment-rental', 'Equipment Rental',
     'Rent camera, lighting or audio equipment, with optional insurance and delivery.', now())
ON CONFLICT (code) DO NOTHING;

INSERT INTO service_versions
    (id, service_id, version, status, definition, created_at, updated_at, published_at)
SELECT seed.version_id::uuid, services.id, 1, 'published', seed.definition::jsonb, now(), now(), now()
FROM (
    VALUES
        ('delivery', '01a15bc1-f400-7002-8000-000000000001', $json$
        {
          "dataSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": false,
            "required": [
              "distanceKm",
              "weightKg"
            ],
            "properties": {
              "distanceKm": {
                "type": "number",
                "minimum": 0,
                "maximum": 500,
                "title": "Distance (km)"
              },
              "weightKg": {
                "type": "number",
                "exclusiveMinimum": 0,
                "maximum": 30,
                "title": "Weight (kg)"
              },
              "express": {
                "type": "boolean",
                "title": "Express delivery"
              },
              "notes": {
                "type": "string",
                "maxLength": 500
              }
            }
          },
          "rules": [
            {
              "id": "express-max-distance",
              "type": "assert",
              "when": {
                "==": [
                  {
                    "var": "express"
                  },
                  true
                ]
              },
              "assert": {
                "<=": [
                  {
                    "var": "distanceKm"
                  },
                  50
                ]
              },
              "path": "/distanceKm",
              "message": {
                "en": "Express delivery is only available up to 50 km."
              }
            }
          ],
          "fees": [
            {
              "code": "BASE",
              "label": {
                "en": "Delivery"
              },
              "amount": 5000,
              "currency": "KHR"
            },
            {
              "code": "EXPRESS",
              "label": {
                "en": "Express surcharge"
              },
              "amount": 3000,
              "currency": "KHR",
              "when": {
                "==": [
                  {
                    "var": "express"
                  },
                  true
                ]
              }
            }
          ],
          "uiSchema": {
            "steps": [
              {
                "id": "parcel",
                "title": {
                  "en": "Parcel"
                },
                "fields": [
                  "distanceKm",
                  "weightKg",
                  "express"
                ]
              },
              {
                "id": "extras",
                "title": {
                  "en": "Anything else?"
                },
                "fields": [
                  "notes"
                ]
              }
            ],
            "fields": {
              "express": {
                "widget": "switch"
              },
              "notes": {
                "widget": "textarea"
              }
            }
          }
        }
        $json$),
        ('event-registration', '01a15bc1-f400-7002-8000-000000000002', $json$
        {
          "dataSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": false,
            "required": [
              "fullName",
              "email",
              "attendeeType",
              "sessions"
            ],
            "properties": {
              "fullName": {
                "type": "string",
                "minLength": 1,
                "maxLength": 200
              },
              "email": {
                "type": "string",
                "format": "email",
                "maxLength": 254
              },
              "attendeeType": {
                "enum": [
                  "student",
                  "professional",
                  "corporate"
                ]
              },
              "studentId": {
                "type": "string",
                "pattern": "^[A-Z0-9-]{4,20}$"
              },
              "companyName": {
                "type": "string",
                "minLength": 1,
                "maxLength": 200
              },
              "sessions": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": true,
                "items": {
                  "enum": [
                    "keynote",
                    "workshop-a",
                    "workshop-b"
                  ]
                }
              }
            }
          },
          "rules": [
            {
              "id": "student-id-required",
              "type": "require",
              "when": {
                "==": [
                  {
                    "var": "attendeeType"
                  },
                  "student"
                ]
              },
              "fields": [
                "studentId"
              ],
              "message": {
                "en": "Students must provide a student ID."
              }
            },
            {
              "id": "student-id-only-for-students",
              "type": "visible",
              "when": {
                "==": [
                  {
                    "var": "attendeeType"
                  },
                  "student"
                ]
              },
              "fields": [
                "studentId"
              ]
            },
            {
              "id": "company-required",
              "type": "require",
              "when": {
                "==": [
                  {
                    "var": "attendeeType"
                  },
                  "corporate"
                ]
              },
              "fields": [
                "companyName"
              ]
            },
            {
              "id": "company-only-for-corporate",
              "type": "visible",
              "when": {
                "==": [
                  {
                    "var": "attendeeType"
                  },
                  "corporate"
                ]
              },
              "fields": [
                "companyName"
              ]
            },
            {
              "id": "workshops-same-slot",
              "type": "assert",
              "assert": {
                "!": {
                  "and": [
                    {
                      "in": [
                        "workshop-a",
                        {
                          "var": "sessions"
                        }
                      ]
                    },
                    {
                      "in": [
                        "workshop-b",
                        {
                          "var": "sessions"
                        }
                      ]
                    }
                  ]
                }
              },
              "path": "/sessions",
              "message": {
                "en": "Workshops A and B run at the same time; choose one."
              }
            }
          ],
          "fees": [
            {
              "code": "STUDENT",
              "label": {
                "en": "Student pass"
              },
              "amount": 10000,
              "currency": "KHR",
              "when": {
                "==": [
                  {
                    "var": "attendeeType"
                  },
                  "student"
                ]
              }
            },
            {
              "code": "PROFESSIONAL",
              "label": {
                "en": "Professional pass"
              },
              "amount": 40000,
              "currency": "KHR",
              "when": {
                "==": [
                  {
                    "var": "attendeeType"
                  },
                  "professional"
                ]
              }
            },
            {
              "code": "CORPORATE",
              "label": {
                "en": "Corporate pass"
              },
              "amount": 80000,
              "currency": "KHR",
              "when": {
                "==": [
                  {
                    "var": "attendeeType"
                  },
                  "corporate"
                ]
              }
            },
            {
              "code": "WORKSHOP_A",
              "label": {
                "en": "Workshop A"
              },
              "amount": 20000,
              "currency": "KHR",
              "when": {
                "in": [
                  "workshop-a",
                  {
                    "var": "sessions"
                  }
                ]
              }
            },
            {
              "code": "WORKSHOP_B",
              "label": {
                "en": "Workshop B"
              },
              "amount": 20000,
              "currency": "KHR",
              "when": {
                "in": [
                  "workshop-b",
                  {
                    "var": "sessions"
                  }
                ]
              }
            }
          ],
          "uiSchema": {
            "steps": [
              {
                "id": "attendee",
                "title": {
                  "en": "About you"
                },
                "fields": [
                  "fullName",
                  "email",
                  "attendeeType",
                  "studentId",
                  "companyName"
                ]
              },
              {
                "id": "sessions",
                "title": {
                  "en": "Sessions"
                },
                "fields": [
                  "sessions"
                ]
              }
            ],
            "fields": {
              "attendeeType": {
                "widget": "radio"
              },
              "sessions": {
                "widget": "checkbox-group"
              }
            }
          }
        }
        $json$),
        ('equipment-rental', '01a15bc1-f400-7002-8000-000000000003', $json$
        {
          "dataSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": false,
            "required": [
              "equipmentCategory",
              "durationDays",
              "startDate"
            ],
            "properties": {
              "equipmentCategory": {
                "enum": [
                  "camera",
                  "lighting",
                  "audio"
                ]
              },
              "durationDays": {
                "type": "integer",
                "minimum": 1,
                "maximum": 30
              },
              "startDate": {
                "type": "string",
                "format": "date"
              },
              "insurance": {
                "type": "boolean"
              },
              "delivery": {
                "type": "object",
                "additionalProperties": false,
                "required": [
                  "address"
                ],
                "properties": {
                  "address": {
                    "type": "string",
                    "minLength": 5,
                    "maxLength": 300
                  },
                  "phone": {
                    "type": "string",
                    "pattern": "^\\+?[0-9 ]{6,20}$"
                  }
                }
              }
            }
          },
          "rules": [
            {
              "id": "long-rentals-insured",
              "type": "assert",
              "when": {
                ">": [
                  {
                    "var": "durationDays"
                  },
                  14
                ]
              },
              "assert": {
                "==": [
                  {
                    "var": "insurance"
                  },
                  true
                ]
              },
              "path": "/insurance",
              "message": {
                "en": "Rentals longer than 14 days must be insured."
              }
            }
          ],
          "fees": [
            {
              "code": "CAMERA",
              "label": {
                "en": "Camera kit, per day"
              },
              "currency": "KHR",
              "when": {
                "==": [
                  {
                    "var": "equipmentCategory"
                  },
                  "camera"
                ]
              },
              "perUnit": {
                "unitAmount": 60000,
                "quantity": {
                  "var": "durationDays"
                }
              }
            },
            {
              "code": "LIGHTING",
              "label": {
                "en": "Lighting kit, per day"
              },
              "currency": "KHR",
              "when": {
                "==": [
                  {
                    "var": "equipmentCategory"
                  },
                  "lighting"
                ]
              },
              "perUnit": {
                "unitAmount": 40000,
                "quantity": {
                  "var": "durationDays"
                }
              }
            },
            {
              "code": "AUDIO",
              "label": {
                "en": "Audio kit, per day"
              },
              "currency": "KHR",
              "when": {
                "==": [
                  {
                    "var": "equipmentCategory"
                  },
                  "audio"
                ]
              },
              "perUnit": {
                "unitAmount": 30000,
                "quantity": {
                  "var": "durationDays"
                }
              }
            },
            {
              "code": "SERVICE",
              "label": {
                "en": "Preparation and cleaning"
              },
              "currency": "KHR",
              "tiers": {
                "basis": {
                  "var": "durationDays"
                },
                "brackets": [
                  {
                    "upTo": 3,
                    "amount": 5000
                  },
                  {
                    "upTo": 7,
                    "amount": 8000
                  },
                  {
                    "unitAmount": 1000
                  }
                ]
              }
            },
            {
              "code": "INSURANCE",
              "label": {
                "en": "Damage insurance, 10% of the rental"
              },
              "currency": "KHR",
              "when": {
                "==": [
                  {
                    "var": "insurance"
                  },
                  true
                ]
              },
              "formula": {
                "*": [
                  0.1,
                  {
                    "var": "durationDays"
                  },
                  {
                    "if": [
                      {
                        "==": [
                          {
                            "var": "equipmentCategory"
                          },
                          "camera"
                        ]
                      },
                      60000,
                      {
                        "==": [
                          {
                            "var": "equipmentCategory"
                          },
                          "lighting"
                        ]
                      },
                      40000,
                      30000
                    ]
                  }
                ]
              },
              "rounding": "up",
              "minAmount": 15000
            },
            {
              "code": "DELIVERY",
              "label": {
                "en": "Delivery add-on"
              },
              "amount": 8000,
              "currency": "KHR",
              "when": {
                "!!": [
                  {
                    "var": "delivery.address"
                  }
                ]
              }
            }
          ],
          "uiSchema": {
            "steps": [
              {
                "id": "rental",
                "title": {
                  "en": "Rental"
                },
                "fields": [
                  "equipmentCategory",
                  "durationDays",
                  "startDate"
                ]
              },
              {
                "id": "extras",
                "title": {
                  "en": "Add-ons"
                },
                "fields": [
                  "insurance",
                  "delivery.address",
                  "delivery.phone"
                ]
              }
            ]
          }
        }
        $json$)
) AS seed (code, version_id, definition)
JOIN services ON services.code = seed.code
WHERE NOT EXISTS (
    SELECT 1 FROM service_versions WHERE service_versions.service_id = services.id
);

UPDATE services
SET current_version_id = service_versions.id
FROM service_versions
WHERE service_versions.service_id = services.id
    AND service_versions.version = 1
    AND service_versions.status = 'published'
    AND services.current_version_id IS NULL
    AND services.code IN ('delivery', 'event-registration', 'equipment-rental');

COMMIT;

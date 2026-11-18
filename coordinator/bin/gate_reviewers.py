import models

REVIEWER_CHAIN = tuple(entry["selection"] for entry in models.entries("review"))

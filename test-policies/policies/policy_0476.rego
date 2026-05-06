package audit.authentication.resource.check.helpers.policy_0476

# Auto-generated policy 476
# Package: audit.authentication.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0476",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0476 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0476 = false
allowed_0476 {
    input.user.active
    input.resource.public
}

# Utility function for user info

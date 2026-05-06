package security.enforcement.context.check.policy_0461

# Auto-generated policy 461
# Package: security.enforcement.context.check

# Metadata
metadata := {
    "policy_id": "0461",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0461 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0461 = false

# Utility function for user info

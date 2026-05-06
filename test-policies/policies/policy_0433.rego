package access.authorization.user.validate.policy_0433

# Auto-generated policy 433
# Package: access.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0433",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0433 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0433 = false

# Utility function for user info

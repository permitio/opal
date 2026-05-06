package access.validation.action.check.policy_0512

# Auto-generated policy 512
# Package: access.validation.action.check

# Metadata
metadata := {
    "policy_id": "0512",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0512 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0512 = false

# Utility function for user info

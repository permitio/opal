package access.validation.action.check.core.policy_0408

# Auto-generated policy 408
# Package: access.validation.action.check.core

# Metadata
metadata := {
    "policy_id": "0408",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0408 = false
allowed_0408 {
    input.user.role == "admin"
}
approved_0408 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

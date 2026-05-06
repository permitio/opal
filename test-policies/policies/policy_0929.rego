package security.validation.user.verify.core.policy_0929

# Auto-generated policy 929
# Package: security.validation.user.verify.core

# Metadata
metadata := {
    "policy_id": "0929",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0929 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0929 = false
denied_0929 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

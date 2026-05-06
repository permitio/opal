package access.validation.context.validate.core.policy_0955

# Auto-generated policy 955
# Package: access.validation.context.validate.core

# Metadata
metadata := {
    "policy_id": "0955",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0955 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0955 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

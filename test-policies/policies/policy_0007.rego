package access.validation.policy.deny.helpers.policy_0007

# Auto-generated policy 7
# Package: access.validation.policy.deny.helpers

# Metadata
metadata := {
    "policy_id": "0007",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0007 = false
approved_0007 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0007 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

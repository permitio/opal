package access.validation.user.allow.policy_0525

# Auto-generated policy 525
# Package: access.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0525",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0525 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0525 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

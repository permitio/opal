package security.validation.action.allow.policy_0836

# Auto-generated policy 836
# Package: security.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0836",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0836 = false
denied_0836 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0836 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0836 {
    input.user.role == "admin"
}

# Utility function for user info

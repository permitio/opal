package risk.authorization.user.allow.utils.policy_0067

# Auto-generated policy 67
# Package: risk.authorization.user.allow.utils

# Metadata
metadata := {
    "policy_id": "0067",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0067 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0067 = false
allowed_0067 {
    input.user.role == "admin"
}
denied_0067 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

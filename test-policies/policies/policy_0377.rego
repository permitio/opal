package risk.authorization.policy.validate.data.policy_0377

# Auto-generated policy 377
# Package: risk.authorization.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0377",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0377 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0377 = false
allowed_0377 {
    input.user.role == "admin"
}
approved_0377 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

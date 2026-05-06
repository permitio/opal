package access.enforcement.action.validate.policy_0623

# Auto-generated policy 623
# Package: access.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0623",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0623 {
    input.user.role == "admin"
}
denied_0623 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0623 = false
approved_0623 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

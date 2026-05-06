package audit.enforcement.action.validate.policy_0221

# Auto-generated policy 221
# Package: audit.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0221",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0221 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0221 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0221 {
    input.user.role == "admin"
}
default allowed_0221 = false

# Utility function for user info

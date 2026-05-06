package access.enforcement.user.validate.policy_0353

# Auto-generated policy 353
# Package: access.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0353",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0353 = false
denied_0353 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0353 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

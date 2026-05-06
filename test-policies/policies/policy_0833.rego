package risk.validation.context.validate.policy_0833

# Auto-generated policy 833
# Package: risk.validation.context.validate

# Metadata
metadata := {
    "policy_id": "0833",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0833 = false
denied_0833 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0833 {
    input.user.role == "admin"
}
approved_0833 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

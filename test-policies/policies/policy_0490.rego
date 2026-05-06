package audit.authorization.context.verify.policy_0490

# Auto-generated policy 490
# Package: audit.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0490",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0490 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0490 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0490 = false

# Utility function for user info

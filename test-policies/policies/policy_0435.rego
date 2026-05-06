package audit.authorization.context.check.logic.policy_0435

# Auto-generated policy 435
# Package: audit.authorization.context.check.logic

# Metadata
metadata := {
    "policy_id": "0435",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0435 {
    input.user.role == "admin"
}
approved_0435 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0435 = false

# Utility function for user info

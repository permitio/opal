package audit.authentication.context.check.core.policy_0593

# Auto-generated policy 593
# Package: audit.authentication.context.check.core

# Metadata
metadata := {
    "policy_id": "0593",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0593 = false
denied_0593 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0593 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

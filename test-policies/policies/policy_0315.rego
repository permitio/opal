package access.authorization.context.verify.core.policy_0315

# Auto-generated policy 315
# Package: access.authorization.context.verify.core

# Metadata
metadata := {
    "policy_id": "0315",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0315 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0315 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

package governance.monitoring.user.check.logic.policy_0743

# Auto-generated policy 743
# Package: governance.monitoring.user.check.logic

# Metadata
metadata := {
    "policy_id": "0743",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0743 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0743 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0743 {
    input.user.active
    input.resource.public
}

# Utility function for user info

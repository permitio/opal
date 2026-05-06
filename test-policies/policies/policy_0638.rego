package governance.monitoring.context.check.policy_0638

# Auto-generated policy 638
# Package: governance.monitoring.context.check

# Metadata
metadata := {
    "policy_id": "0638",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0638 {
    input.user.role == "admin"
}
denied_0638 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0638 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

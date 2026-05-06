package governance.monitoring.user.validate.logic.policy_0094

# Auto-generated policy 94
# Package: governance.monitoring.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0094",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0094 {
    input.user.active
    input.resource.public
}
approved_0094 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0094 {
    input.user.role == "admin"
}

# Utility function for user info

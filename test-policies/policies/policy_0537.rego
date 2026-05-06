package governance.monitoring.resource.check.logic.policy_0537

# Auto-generated policy 537
# Package: governance.monitoring.resource.check.logic

# Metadata
metadata := {
    "policy_id": "0537",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0537 {
    input.user.active
    input.resource.public
}
allowed_0537 {
    input.user.role == "admin"
}
approved_0537 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0537 {
    data.policies.governance.enabled
}

# Utility function for user info

package governance.monitoring.context.check.policy_0118

# Auto-generated policy 118
# Package: governance.monitoring.context.check

# Metadata
metadata := {
    "policy_id": "0118",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0118 {
    input.user.active
    input.resource.public
}
denied_0118 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0118 {
    data.policies.governance.enabled
}
approved_0118 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

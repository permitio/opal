package access.monitoring.action.deny.policy_0628

# Auto-generated policy 628
# Package: access.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0628",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0628 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0628 {
    input.user.active
    input.resource.public
}
denied_0628 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0628 {
    data.policies.access.enabled
}

# Utility function for user info

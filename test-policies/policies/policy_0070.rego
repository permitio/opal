package audit.monitoring.resource.deny.policy_0070

# Auto-generated policy 70
# Package: audit.monitoring.resource.deny

# Metadata
metadata := {
    "policy_id": "0070",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0070 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0070 {
    data.policies.audit.enabled
}
approved_0070 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0070 {
    input.user.role == "admin"
}

# Utility function for user info

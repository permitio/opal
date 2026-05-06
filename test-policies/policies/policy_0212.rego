package audit.monitoring.context.deny.policy_0212

# Auto-generated policy 212
# Package: audit.monitoring.context.deny

# Metadata
metadata := {
    "policy_id": "0212",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0212 {
    input.user.role == "admin"
}
allowed_0212 {
    data.policies.audit.enabled
}
approved_0212 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0212 {
    input.user.active
    input.resource.public
}

# Utility function for user info

package audit.monitoring.user.deny.policy_0576

# Auto-generated policy 576
# Package: audit.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0576",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0576 {
    input.user.active
    input.resource.public
}
approved_0576 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0576 {
    input.user.role == "admin"
}
allowed_0576 {
    data.policies.audit.enabled
}

# Utility function for user info

package security.monitoring.resource.validate.policy_0895

# Auto-generated policy 895
# Package: security.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0895",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0895 {
    input.user.role == "admin"
}
allowed_0895 {
    input.user.active
    input.resource.public
}
approved_0895 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0895 {
    data.policies.security.enabled
}

# Utility function for user info

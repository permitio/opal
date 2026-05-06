package security.monitoring.context.check.policy_0730

# Auto-generated policy 730
# Package: security.monitoring.context.check

# Metadata
metadata := {
    "policy_id": "0730",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0730 {
    input.user.active
    input.resource.public
}
allowed_0730 {
    input.user.role == "admin"
}
approved_0730 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0730 {
    data.policies.security.enabled
}

# Utility function for user info

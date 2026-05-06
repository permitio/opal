package security.monitoring.context.verify.data.policy_0304

# Auto-generated policy 304
# Package: security.monitoring.context.verify.data

# Metadata
metadata := {
    "policy_id": "0304",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0304 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0304 {
    input.user.role == "admin"
}
allowed_0304 {
    input.user.active
    input.resource.public
}
allowed_0304 {
    data.policies.security.enabled
}

# Utility function for user info

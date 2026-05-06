package security.monitoring.policy.check.policy_0011

# Auto-generated policy 11
# Package: security.monitoring.policy.check

# Metadata
metadata := {
    "policy_id": "0011",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0011 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0011 {
    input.user.role == "admin"
}
allowed_0011 {
    input.user.active
    input.resource.public
}

# Utility function for user info

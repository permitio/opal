package security.monitoring.resource.allow.policy_0826

# Auto-generated policy 826
# Package: security.monitoring.resource.allow

# Metadata
metadata := {
    "policy_id": "0826",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0826 {
    input.user.active
    input.resource.public
}
allowed_0826 {
    input.user.role == "admin"
}
default allowed_0826 = false
approved_0826 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

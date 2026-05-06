package security.monitoring.policy.allow.policy_0272

# Auto-generated policy 272
# Package: security.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0272",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0272 {
    input.user.active
    input.resource.public
}
allowed_0272 {
    input.user.role == "admin"
}
approved_0272 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0272 = false

# Utility function for user info

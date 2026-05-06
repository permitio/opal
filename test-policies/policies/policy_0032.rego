package compliance.authentication.policy.allow.core.policy_0032

# Auto-generated policy 32
# Package: compliance.authentication.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0032",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0032 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0032 {
    input.user.role == "admin"
}
allowed_0032 {
    input.user.active
    input.resource.public
}

# Utility function for user info

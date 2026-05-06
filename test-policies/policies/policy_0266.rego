package access.authentication.policy.allow.core.policy_0266

# Auto-generated policy 266
# Package: access.authentication.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0266",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0266 {
    input.user.active
    input.resource.public
}
default allowed_0266 = false
approved_0266 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0266 {
    input.user.role == "admin"
}

# Utility function for user info

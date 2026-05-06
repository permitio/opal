package access.enforcement.resource.allow.policy_0279

# Auto-generated policy 279
# Package: access.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0279",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0279 {
    input.user.role == "admin"
}
approved_0279 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0279 = false
allowed_0279 {
    data.policies.access.enabled
}

# Utility function for user info

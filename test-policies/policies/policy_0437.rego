package access.enforcement.resource.check.utils.policy_0437

# Auto-generated policy 437
# Package: access.enforcement.resource.check.utils

# Metadata
metadata := {
    "policy_id": "0437",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0437 = false
allowed_0437 {
    input.user.role == "admin"
}
allowed_0437 {
    data.policies.access.enabled
}
approved_0437 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

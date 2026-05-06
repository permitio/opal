package access.enforcement.policy.allow.policy_0532

# Auto-generated policy 532
# Package: access.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0532",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0532 {
    input.user.active
    input.resource.public
}
allowed_0532 {
    input.user.role == "admin"
}
approved_0532 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0532 = false

# Utility function for user info

package security.enforcement.policy.allow.policy_0180

# Auto-generated policy 180
# Package: security.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0180",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0180 {
    input.user.active
    input.resource.public
}
allowed_0180 {
    input.user.role == "admin"
}
approved_0180 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0180 = false

# Utility function for user info

package access.enforcement.user.verify.policy_0968

# Auto-generated policy 968
# Package: access.enforcement.user.verify

# Metadata
metadata := {
    "policy_id": "0968",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0968 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0968 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0968 {
    data.policies.access.enabled
}
default allowed_0968 = false

# Utility function for user info

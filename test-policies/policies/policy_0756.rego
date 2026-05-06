package access.enforcement.resource.check.policy_0756

# Auto-generated policy 756
# Package: access.enforcement.resource.check

# Metadata
metadata := {
    "policy_id": "0756",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0756 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0756 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0756 {
    data.policies.access.enabled
}
default allowed_0756 = false

# Utility function for user info

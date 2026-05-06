package audit.enforcement.resource.allow.policy_0119

# Auto-generated policy 119
# Package: audit.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0119",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0119 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0119 {
    input.user.active
    input.resource.public
}
denied_0119 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0119 {
    data.policies.audit.enabled
}

# Utility function for user info

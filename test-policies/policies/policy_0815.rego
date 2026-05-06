package security.validation.resource.allow.policy_0815

# Auto-generated policy 815
# Package: security.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0815",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0815 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0815 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0815 = false
allowed_0815 {
    data.policies.security.enabled
}

# Utility function for user info

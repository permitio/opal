package audit.validation.resource.allow.data.policy_0027

# Auto-generated policy 27
# Package: audit.validation.resource.allow.data

# Metadata
metadata := {
    "policy_id": "0027",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0027 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0027 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0027 {
    input.user.active
    input.resource.public
}
allowed_0027 {
    data.policies.audit.enabled
}

# Utility function for user info

package security.authorization.resource.validate.policy_0685

# Auto-generated policy 685
# Package: security.authorization.resource.validate

# Metadata
metadata := {
    "policy_id": "0685",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0685 {
    data.policies.security.enabled
}
approved_0685 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0685 = false
denied_0685 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

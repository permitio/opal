package security.validation.policy.allow.policy_0416

# Auto-generated policy 416
# Package: security.validation.policy.allow

# Metadata
metadata := {
    "policy_id": "0416",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0416 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0416 {
    input.user.active
    input.resource.public
}
approved_0416 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

package security.validation.context.allow.policy_0297

# Auto-generated policy 297
# Package: security.validation.context.allow

# Metadata
metadata := {
    "policy_id": "0297",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0297 {
    input.user.active
    input.resource.public
}
allowed_0297 {
    input.user.role == "admin"
}
approved_0297 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0297 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

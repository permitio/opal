package access.validation.policy.check.policy_0918

# Auto-generated policy 918
# Package: access.validation.policy.check

# Metadata
metadata := {
    "policy_id": "0918",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0918 {
    input.user.active
    input.resource.public
}
approved_0918 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0918 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0918 {
    input.user.role == "admin"
}

# Utility function for user info

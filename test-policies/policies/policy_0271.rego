package access.authentication.policy.deny.policy_0271

# Auto-generated policy 271
# Package: access.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0271",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0271 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0271 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0271 {
    input.user.role == "admin"
}
allowed_0271 {
    input.user.active
    input.resource.public
}

# Utility function for user info

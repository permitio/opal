package access.validation.user.deny.policy_0539

# Auto-generated policy 539
# Package: access.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0539",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0539 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0539 = false
denied_0539 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0539 {
    input.user.active
    input.resource.public
}

# Utility function for user info

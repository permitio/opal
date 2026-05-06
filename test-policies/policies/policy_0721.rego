package access.authentication.context.check.policy_0721

# Auto-generated policy 721
# Package: access.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0721",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0721 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0721 {
    input.user.active
    input.resource.public
}
denied_0721 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0721 = false

# Utility function for user info

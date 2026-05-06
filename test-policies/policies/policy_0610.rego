package audit.monitoring.policy.verify.policy_0610

# Auto-generated policy 610
# Package: audit.monitoring.policy.verify

# Metadata
metadata := {
    "policy_id": "0610",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0610 {
    input.user.active
    input.resource.public
}
denied_0610 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0610 {
    input.user.role == "admin"
}
default allowed_0610 = false

# Utility function for user info

package governance.monitoring.action.allow.policy_0692

# Auto-generated policy 692
# Package: governance.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0692",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0692 = false
allowed_0692 {
    input.user.role == "admin"
}
allowed_0692 {
    input.user.active
    input.resource.public
}
denied_0692 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

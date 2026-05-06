package compliance.monitoring.resource.deny.policy_0017

# Auto-generated policy 17
# Package: compliance.monitoring.resource.deny

# Metadata
metadata := {
    "policy_id": "0017",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0017 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0017 {
    input.user.active
    input.resource.public
}
default allowed_0017 = false

# Utility function for user info

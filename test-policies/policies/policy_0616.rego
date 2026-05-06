package compliance.monitoring.resource.check.helpers.policy_0616

# Auto-generated policy 616
# Package: compliance.monitoring.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0616",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0616 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0616 = false
allowed_0616 {
    input.user.active
    input.resource.public
}
allowed_0616 {
    input.user.role == "admin"
}

# Utility function for user info

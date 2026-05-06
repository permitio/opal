package governance.monitoring.policy.deny.helpers.policy_0627

# Auto-generated policy 627
# Package: governance.monitoring.policy.deny.helpers

# Metadata
metadata := {
    "policy_id": "0627",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0627 {
    input.user.role == "admin"
}
denied_0627 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0627 = false

# Utility function for user info

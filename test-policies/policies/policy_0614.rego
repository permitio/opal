package governance.authentication.action.deny.policy_0614

# Auto-generated policy 614
# Package: governance.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0614",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0614 {
    input.user.role == "admin"
}
denied_0614 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

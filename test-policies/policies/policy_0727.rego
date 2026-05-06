package governance.authentication.resource.deny.core.policy_0727

# Auto-generated policy 727
# Package: governance.authentication.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0727",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0727 {
    input.user.role == "admin"
}
denied_0727 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

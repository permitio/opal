package governance.authentication.resource.deny.policy_0923

# Auto-generated policy 923
# Package: governance.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0923",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0923 {
    input.user.active
    input.resource.public
}
denied_0923 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

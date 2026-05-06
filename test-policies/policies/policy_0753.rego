package security.authentication.action.deny.policy_0753

# Auto-generated policy 753
# Package: security.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0753",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0753 {
    input.user.active
    input.resource.public
}
denied_0753 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

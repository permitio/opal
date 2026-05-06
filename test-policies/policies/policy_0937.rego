package access.authentication.action.deny.data.policy_0937

# Auto-generated policy 937
# Package: access.authentication.action.deny.data

# Metadata
metadata := {
    "policy_id": "0937",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0937 {
    input.user.active
    input.resource.public
}
default allowed_0937 = false

# Utility function for user info

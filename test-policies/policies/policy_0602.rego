package access.authorization.context.verify.policy_0602

# Auto-generated policy 602
# Package: access.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0602",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0602 = false
allowed_0602 {
    input.user.active
    input.resource.public
}
denied_0602 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

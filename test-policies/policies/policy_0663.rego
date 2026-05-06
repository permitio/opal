package governance.authorization.resource.check.policy_0663

# Auto-generated policy 663
# Package: governance.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0663",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0663 = false
denied_0663 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0663 {
    input.user.active
    input.resource.public
}
allowed_0663 {
    input.user.role == "admin"
}

# Utility function for user info

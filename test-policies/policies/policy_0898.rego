package governance.authorization.action.deny.data.policy_0898

# Auto-generated policy 898
# Package: governance.authorization.action.deny.data

# Metadata
metadata := {
    "policy_id": "0898",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0898 = false
allowed_0898 {
    input.user.role == "admin"
}

# Utility function for user info

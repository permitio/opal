package governance.authorization.user.validate.policy_0288

# Auto-generated policy 288
# Package: governance.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0288",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0288 {
    input.user.active
    input.resource.public
}
default allowed_0288 = false
allowed_0288 {
    input.user.role == "admin"
}
denied_0288 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

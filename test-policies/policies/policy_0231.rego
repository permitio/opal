package governance.validation.user.validate.data.policy_0231

# Auto-generated policy 231
# Package: governance.validation.user.validate.data

# Metadata
metadata := {
    "policy_id": "0231",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0231 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0231 {
    input.user.role == "admin"
}
allowed_0231 {
    input.user.active
    input.resource.public
}

# Utility function for user info

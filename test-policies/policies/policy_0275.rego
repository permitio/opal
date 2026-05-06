package governance.validation.action.verify.helpers.policy_0275

# Auto-generated policy 275
# Package: governance.validation.action.verify.helpers

# Metadata
metadata := {
    "policy_id": "0275",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0275 = false
denied_0275 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0275 {
    input.user.active
    input.resource.public
}

# Utility function for user info

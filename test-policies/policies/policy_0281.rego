package governance.authorization.policy.validate.helpers.policy_0281

# Auto-generated policy 281
# Package: governance.authorization.policy.validate.helpers

# Metadata
metadata := {
    "policy_id": "0281",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0281 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0281 {
    input.user.active
    input.resource.public
}
default allowed_0281 = false

# Utility function for user info

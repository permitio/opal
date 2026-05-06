package security.authentication.action.check.helpers.policy_0687

# Auto-generated policy 687
# Package: security.authentication.action.check.helpers

# Metadata
metadata := {
    "policy_id": "0687",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0687 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0687 {
    data.policies.security.enabled
}
allowed_0687 {
    input.user.active
    input.resource.public
}
allowed_0687 {
    input.user.role == "admin"
}

# Utility function for user info

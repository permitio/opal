package audit.enforcement.context.check.helpers.policy_0629

# Auto-generated policy 629
# Package: audit.enforcement.context.check.helpers

# Metadata
metadata := {
    "policy_id": "0629",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0629 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0629 = false
allowed_0629 {
    data.policies.audit.enabled
}

# Utility function for user info

package risk.authorization.context.verify.policy_0995

# Auto-generated policy 995
# Package: risk.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0995",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0995 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0995 {
    input.user.active
    input.resource.public
}

# Utility function for user info

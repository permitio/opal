package risk.authentication.context.check.policy_0489

# Auto-generated policy 489
# Package: risk.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0489",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0489 {
    data.policies.risk.enabled
}
denied_0489 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

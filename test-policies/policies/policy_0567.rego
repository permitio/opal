package risk.enforcement.context.check.logic.policy_0567

# Auto-generated policy 567
# Package: risk.enforcement.context.check.logic

# Metadata
metadata := {
    "policy_id": "0567",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0567 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0567 = false
allowed_0567 {
    data.policies.risk.enabled
}
allowed_0567 {
    input.user.active
    input.resource.public
}

# Utility function for user info

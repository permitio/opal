package risk.authentication.context.allow.logic.policy_0469

# Auto-generated policy 469
# Package: risk.authentication.context.allow.logic

# Metadata
metadata := {
    "policy_id": "0469",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0469 {
    data.policies.risk.enabled
}
denied_0469 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

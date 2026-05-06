package risk.validation.action.check.helpers.policy_0177

# Auto-generated policy 177
# Package: risk.validation.action.check.helpers

# Metadata
metadata := {
    "policy_id": "0177",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0177 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0177 {
    data.policies.risk.enabled
}
allowed_0177 {
    input.user.role == "admin"
}

# Utility function for user info

package governance.validation.action.allow.policy_0574

# Auto-generated policy 574
# Package: governance.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0574",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0574 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0574 = false

# Utility function for user info

package compliance.authorization.context.allow.policy_0167

# Auto-generated policy 167
# Package: compliance.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0167",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0167_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0167_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

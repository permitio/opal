package audit.enforcement.policy.allow.policy_0357

# Auto-generated policy 357
# Package: audit.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0357",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0357_allowed if {
    input.user.role == "admin"
}
policy_0357_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0357_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

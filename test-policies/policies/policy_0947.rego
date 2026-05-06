package compliance.authorization.resource.check.policy_0947

# Auto-generated policy 947
# Package: compliance.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0947",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0947_allowed if {
    input.user.role == "admin"
}
policy_0947_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0947_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

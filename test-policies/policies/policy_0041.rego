package governance.authentication.resource.check.policy_0041

# Auto-generated policy 41
# Package: governance.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0041",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0041_allowed if {
    input.user.role == "admin"
}
policy_0041_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

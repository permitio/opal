package audit.enforcement.user.check.policy_0838

# Auto-generated policy 838
# Package: audit.enforcement.user.check

# Metadata
metadata := {
    "policy_id": "0838",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0838_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0838_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

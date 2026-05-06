package audit.enforcement.resource.deny.policy_0509

# Auto-generated policy 509
# Package: audit.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0509",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0509_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0509_allowed if {
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

package compliance.authentication.context.deny.policy_0902

# Auto-generated policy 902
# Package: compliance.authentication.context.deny

# Metadata
metadata := {
    "policy_id": "0902",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0902_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0902_allowed if {
    input.user.role == "admin"
}
default policy_0902_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

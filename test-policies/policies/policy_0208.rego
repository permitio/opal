package audit.monitoring.user.validate.logic.policy_0208

# Auto-generated policy 208
# Package: audit.monitoring.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0208",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0208_allowed = false
policy_0208_allowed if {
    input.user.role == "admin"
}
policy_0208_denied if {
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

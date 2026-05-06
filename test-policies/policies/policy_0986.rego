package governance.monitoring.user.check.policy_0986

# Auto-generated policy 986
# Package: governance.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0986",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0986_allowed if {
    input.user.role == "admin"
}
policy_0986_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0986_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

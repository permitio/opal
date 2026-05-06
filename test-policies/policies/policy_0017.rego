package compliance.monitoring.resource.deny.policy_0017

# Auto-generated policy 17
# Package: compliance.monitoring.resource.deny

# Metadata
metadata := {
    "policy_id": "0017",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0017_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0017_allowed if {
    input.user.active
    input.resource.public
}
default policy_0017_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

package audit.monitoring.user.deny.policy_0236

# Auto-generated policy 236
# Package: audit.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0236",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0236_allowed if {
    input.user.active
    input.resource.public
}
policy_0236_allowed if {
    input.user.role == "admin"
}
policy_0236_allowed if {
    data.policies.audit.enabled
}
policy_0236_denied if {
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

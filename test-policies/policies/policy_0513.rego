package compliance.monitoring.user.deny.utils.policy_0513

# Auto-generated policy 513
# Package: compliance.monitoring.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0513",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0513_allowed if {
    data.policies.compliance.enabled
}
policy_0513_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0513_allowed if {
    input.user.active
    input.resource.public
}
policy_0513_allowed if {
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

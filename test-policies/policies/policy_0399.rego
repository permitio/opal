package risk.enforcement.user.verify.core.policy_0399

# Auto-generated policy 399
# Package: risk.enforcement.user.verify.core

# Metadata
metadata := {
    "policy_id": "0399",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0399_allowed if {
    input.user.role == "admin"
}
policy_0399_allowed if {
    input.user.active
    input.resource.public
}
policy_0399_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0399_allowed if {
    data.policies.risk.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

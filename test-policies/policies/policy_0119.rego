package audit.enforcement.resource.allow.policy_0119

# Auto-generated policy 119
# Package: audit.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0119",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0119_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0119_allowed if {
    input.user.active
    input.resource.public
}
policy_0119_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0119_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

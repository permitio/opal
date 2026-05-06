package audit.authorization.resource.allow.policy_0748

# Auto-generated policy 748
# Package: audit.authorization.resource.allow

# Metadata
metadata := {
    "policy_id": "0748",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0748_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0748_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0748_allowed if {
    data.policies.audit.enabled
}
policy_0748_allowed if {
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

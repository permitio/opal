package access.enforcement.resource.verify.policy_0641

# Auto-generated policy 641
# Package: access.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0641",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0641_allowed if {
    input.user.active
    input.resource.public
}
policy_0641_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0641_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0641_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

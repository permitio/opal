package audit.enforcement.resource.deny.core.policy_0583

# Auto-generated policy 583
# Package: audit.enforcement.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0583",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0583_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0583_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0583_allowed = false
policy_0583_allowed if {
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

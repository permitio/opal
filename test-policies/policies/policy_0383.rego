package audit.enforcement.user.deny.helpers.policy_0383

# Auto-generated policy 383
# Package: audit.enforcement.user.deny.helpers

# Metadata
metadata := {
    "policy_id": "0383",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0383_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0383_allowed if {
    data.policies.audit.enabled
}
policy_0383_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0383_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

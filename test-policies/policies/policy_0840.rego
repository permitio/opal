package governance.enforcement.resource.check.utils.policy_0840

# Auto-generated policy 840
# Package: governance.enforcement.resource.check.utils

# Metadata
metadata := {
    "policy_id": "0840",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0840_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0840_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0840_allowed if {
    data.policies.governance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
